import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  const { messages, thread_id } = await req.json();
  const apiKey = req.headers.get('X-API-Key') || process.env.LANGGRAPH_API_KEY || '';

  // Call the FastAPI /invoke endpoint
  const response = await fetch('http://langgraph-server:8000/invoke', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({
      input: { messages },
      config: { configurable: { thread_id: thread_id || crypto.randomUUID() } },
    }),
  });

  const data = await response.json();

  // Optionally store conversation in Odoo via odoo-proxy
  if (thread_id && data.analysis) {
    try {
      // Update or create conversation in Odoo
      const storeRes = await fetch('http://odoo-proxy:8080/jsonrpc', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          method: 'call',
          params: {
            service: 'object',
            method: 'execute_kw',
            args: [
              'odoo',                // database
              1,                     // uid (system user)
              '',                    // password (unused with API key)
              'nettrades_chatbot_conversations',
              'search_read',
              [[['session_id', '=', thread_id]]],
              { fields: ['id', 'messages'] },
            ],
          },
          id: 1,
        }),
      });
      const storeData = await storeRes.json();
      const records = storeData.result || [];

      if (records.length > 0) {
        // Update existing record
        const recordId = records[0].id;
        let existingMsgs = [];
        try {
          existingMsgs = JSON.parse(records[0].messages);
        } catch (_) {}
        const newMessages = [...existingMsgs, ...messages, { role: 'assistant', content: data.analysis }];
        await fetch('http://odoo-proxy:8080/jsonrpc', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey,
          },
          body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            params: {
              service: 'object',
              method: 'execute_kw',
              args: [
                'odoo',
                1,
                '',
                'nettrades_chatbot_conversations',
                'write',
                [[recordId], { messages: JSON.stringify(newMessages) }],
              ],
            },
            id: 2,
          }),
        });
      } else {
        // Create new record
        await fetch('http://odoo-proxy:8080/jsonrpc', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey,
          },
          body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            params: {
              service: 'object',
              method: 'execute_kw',
              args: [
                'odoo',
                1,
                '',
                'nettrades_chatbot_conversations',
                'create',
                [{
                  session_id: thread_id,
                  messages: JSON.stringify([...messages, { role: 'assistant', content: data.analysis }]),
                }],
              ],
            },
            id: 2,
          }),
        });
      }
    } catch (err) {
      console.warn('Failed to store chat history in Odoo:', err);
    }
  }

  return NextResponse.json(data);
}