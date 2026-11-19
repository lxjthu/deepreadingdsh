"""Mirror durable cards into a user-selected folder without overwriting external edits."""
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path


def sha(data): return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(data)
        os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)


class NoteFiles:
    """Own generated note filenames and remember the last bytes written at each destination."""
    def __init__(self, store):
        self.store=store
        with store.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS card_note_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS card_note_files(root TEXT NOT NULL,card_id TEXT NOT NULL,path TEXT NOT NULL,last_hash TEXT,error TEXT,updated REAL NOT NULL,PRIMARY KEY(root,card_id));
            ''')
        saved=store.rows("SELECT value FROM card_note_settings WHERE key='folder'")
        self.root=Path(saved[0]['value']) if saved else store.home/'card-notes'

    def status(self):
        errors=self.store.rows('SELECT card_id,error FROM card_note_files WHERE root=? AND error IS NOT NULL',(str(self.root),))
        return {'folder':str(self.root),'imagesFolder':str(self.root/'images'),'errors':errors}

    @staticmethod
    def prepare(value):
        if not isinstance(value,str) or not value.strip():raise ValueError('请填写卡片笔记目录')
        root=Path(value)
        if not root.is_absolute(): raise ValueError('卡片笔记目录必须是完整绝对路径')
        root=root.resolve()
        root.mkdir(parents=True,exist_ok=True)
        assets=root/'images'
        if assets.is_symlink(): raise ValueError('图片目录不能是符号链接')
        assets.mkdir(exist_ok=True)
        probe=root/('.dsh-write-probe-'+uuid.uuid4().hex)
        try: probe.write_text('probe',encoding='utf-8')
        finally: probe.unlink(missing_ok=True)
        return root

    def configure(self, value):
        with self.store.mutex:
            if not self.store.accepting:raise ValueError('资料目录正在切换')
            if self.store.active_task or self.store.rows("SELECT id FROM tasks WHERE status IN ('running','queued')"):
                raise ValueError('请先结束运行或排队任务，再修改卡片笔记目录')
            root=self.prepare(value)
            errors=self.rebuild(root)
            if errors: raise ValueError('新目录未启用；有卡片写入失败：'+errors[0]['error'])
            with self.store.db() as db: db.execute("INSERT INTO card_note_settings VALUES('folder',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(root),))
            self.root=root
            return self.status()

    def rebuild(self, root=None):
        errors=[]
        for row in self.store.rows('SELECT payload FROM pdf_cards ORDER BY created'):
            result=self.sync(json.loads(row['payload']),root)
            if result.get('error'): errors.append(result)
        return errors

    def sync(self, card, root=None):
        import pdf_cards
        with self.store.mutex:
            if not isinstance(card.get('id'),str) or not re.fullmatch('[0-9a-f]{32}',card['id']):raise ValueError('卡片文件标识无效')
            current=self.store.rows('SELECT payload FROM pdf_cards WHERE id=?',(card['id'],))
            if current:card=json.loads(current[0]['payload'])
            root=Path(root or self.root)
            path=root/('card-'+card['id']+'.md')
            prior=self.store.rows('SELECT last_hash FROM card_note_files WHERE root=? AND card_id=?',(str(root),card['id']))
            last_hash=prior[0]['last_hash'] if prior else None
            error=None
            try:
                self.prepare(str(root))
                if path.is_symlink(): raise ValueError('笔记文件不能是符号链接')
                if 'paper_metadata' not in card:
                    card={**card,**pdf_cards.paper_properties(self.store,card['entry_id']),'paper_metadata_origin':'current_library'}
                data=pdf_cards.markdown(card).encode('utf-8')
                expected=sha(data)
                if path.exists() and sha(path.read_bytes()) not in (last_hash,expected):
                    raise ValueError('笔记已被外部修改，请先保留该文件并移走或改名，再重试同步：'+str(path))
                for asset in card.get('images',[]):
                    name=asset['sha256']+'.png'
                    if len(asset['sha256'])!=64 or any(char not in '0123456789abcdef' for char in asset['sha256']):raise ValueError('图片哈希无效')
                    source=self.store.workspace.path('visuals/'+name).resolve()
                    if not source.is_relative_to((self.store.workspace.root/'visuals').resolve()):raise ValueError('图片来源越界')
                    image=source.read_bytes()
                    if sha(image)!=asset['sha256']:raise ValueError('原始裁剪图校验失败')
                    target=root/'images'/name
                    if target.is_symlink():raise ValueError('图片文件不能是符号链接')
                    if target.exists() and sha(target.read_bytes())!=asset['sha256']:raise ValueError('图片文件已在外部修改：'+str(target))
                    if not target.exists():atomic_write(target,image)
                if path.exists() and sha(path.read_bytes()) not in (last_hash,expected):raise ValueError('笔记在同步期间被外部修改，未覆盖：'+str(path))
                if not path.exists() or sha(path.read_bytes())!=expected:atomic_write(path,data)
                last_hash=expected
            except (OSError,ValueError) as exc:error=str(exc)
            with self.store.db() as db:
                db.execute('INSERT INTO card_note_files VALUES(?,?,?,?,?,?) ON CONFLICT(root,card_id) DO UPDATE SET path=excluded.path,last_hash=excluded.last_hash,error=excluded.error,updated=excluded.updated',
                           (str(root),card['id'],str(path),last_hash,error,time.time()))
            return {'path':str(path),'error':error}

    def card_status(self, card_id):
        rows=self.store.rows('SELECT path,error FROM card_note_files WHERE root=? AND card_id=?',(str(self.root),card_id))
        return rows[0] if rows else {'path':str(self.root/('card-'+card_id+'.md')),'error':'笔记尚未同步'}
