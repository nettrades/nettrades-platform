import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const sessionId = req.nextUrl.searchParams.get('session_id');
  const apiKey = req.headers.get('X-API-Key') || '';

  if (!sessionId) {
    return NextResponse.json([], { status: 200 });
  }

  try {
    const response = await fetch('http://odoo-proxy:8080/jsonrpc', {
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
            'search_read',
            [[['session_id', '=', sessionId]]],
            { fields: ['messages', 'create_date'] },
          ],
        },
        id: 1,
      }),
    });

    const data = await response.json();
    return NextResponse.json(data.result || []);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to fetch history' }, { status: 500 });
  }
}