/** Translate the business conversation without flattening assistant history. */
export function requestOptions(request, llmMessages, config, signal) {
  const { createAssistantMessage, createSystemMessage, createUserMessage } = llmMessages;
  const lastUser=request.messages.findLastIndex(message=>message.role==='user');
  const messages = request.messages.map((m,index) => {
    const content = [{ type: 'text', text: m.content }];
    if(index===lastUser)for(const attachment of request.imageRefs||[])content.push({type:'image',attachment});
    if (m.role === 'system') return createSystemMessage(m.content);
    if (m.role === 'assistant') return createAssistantMessage({ content, source: { provider: config.provider, model: config.model } });
    if (m.role === 'user') return createUserMessage({ content, source: { kind: 'user' } });
    throw new Error('Unsupported business message role: ' + m.role);
  });
  return { provider: config.provider, model: config.model, messages, ...(config.reasoningEffort === undefined ? {} : { reasoningEffort: config.reasoningEffort }), ...(config.maxTokens === undefined ? {} : { maxTokens: config.maxTokens }), signal };
}

/** Admit actual image bytes and reject routes that would replace them with text placeholders. */
export async function admitVisionRequest(request,llm,attachments,config,signal){
  if(!request.images?.length)return request;
  if(!attachments)throw new Error('当前宿主未提供图片附件服务，无法执行视觉识别');
  const info=await llm.resolveModelInfo(config.provider,config.model,signal);
  if(!info.inputModalities?.includes('image'))throw new Error('当前 Harness 模型不支持图片输入，请选择支持图片的模型后重试视觉识别');
  const images=request.images.map(image=>{
    if(typeof image.data!=='string'||image.mediaType!=='image/png')throw new Error('视觉识别图片格式无效');
    const data=Buffer.from(image.data,'base64');
    if(!data.length||data.toString('base64')!==image.data)throw new Error('视觉识别图片编码无效');
    return {data,mediaType:image.mediaType,name:image.name};
  });
  const imageRefs=await attachments.saveImages(images);
  if(signal.aborted)throw signal.reason||new Error('视觉识别已取消');
  return {...request,imageRefs};
}

export async function generate(llm, options) {
  let text = '', reason, usage;
  for await (const chunk of llm.stream(options)) {
    if (chunk.type === 'text-delta') text += chunk.text;
    if (chunk.type === 'usage') usage = chunk.usage;
    if (chunk.type === 'finish') reason = chunk.reason;
  }
  if (reason?.kind !== 'stop') {
    const error = new Error(reason?.failure?.message || `Model did not complete: ${reason?.kind || 'missing finish'}`);
    error.code = reason?.failure?.code || reason?.kind || 'INCOMPLETE';
    throw error;
  }
  if (!text.trim()) throw new Error('Model returned no visible answer');
  return { content: text, finish_reason: 'stop', reported_model: options.provider + '/' + options.model, usage };
}
