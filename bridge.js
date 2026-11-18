/** Translate the business conversation without flattening assistant history. */
export function requestOptions(request, llmMessages, config, signal) {
  const { createAssistantMessage, createSystemMessage, createUserMessage } = llmMessages;
  const messages = request.messages.map(m => {
    const content = [{ type: 'text', text: m.content }];
    if (m.role === 'system') return createSystemMessage(m.content);
    if (m.role === 'assistant') return createAssistantMessage({ content, source: { provider: config.provider, model: config.model } });
    if (m.role === 'user') return createUserMessage({ content, source: { kind: 'user' } });
    throw new Error('Unsupported business message role: ' + m.role);
  });
  return { provider: config.provider, model: config.model, messages, ...(config.reasoningEffort === undefined ? {} : { reasoningEffort: config.reasoningEffort }), ...(config.maxTokens === undefined ? {} : { maxTokens: config.maxTokens }), signal };
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
