import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';

const ME4BRAIN_URL = process.env.ME4BRAIN_URL ?? 'http://localhost:8089';

async function proxyToMe4BrAIn(
  path: string,
  req: FastifyRequest,
  reply: FastifyReply,
  method: string = 'GET'
) {
  try {
    const url = `${ME4BRAIN_URL}${path}`;
    const options: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (method !== 'GET' && req.body) {
      options.body = JSON.stringify(req.body);
    }

    const response = await fetch(url, options);
    const data = await response.json();

    if (!response.ok) {
      return reply.status(response.status).send(data);
    }

    return reply.send(data);
  } catch (error) {
    req.log.error(error as any, `config_proxy_error: ${path}`);
    return reply.status(502).send({ error: 'Failed to connect to Me4BrAIn' });
  }
}

export async function configRoutes(app: FastifyInstance): Promise<void> {
  app.get('/api/config/llm/current', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/current', req, reply);
  });

  app.get('/api/config/llm/status', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/status', req, reply);
  });

  app.get('/api/config/llm/models', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/models', req, reply);
  });

  app.put('/api/config/llm/update', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/update', req, reply, 'PUT');
  });

  app.post('/api/config/llm/context-tracker/reset', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/context-tracker/reset', req, reply, 'POST');
  });

  app.get('/api/monitoring/resources', async (req: FastifyRequest, reply: FastifyReply) => {
    try {
      const url = `${ME4BRAIN_URL}/v1/monitoring/resources`;
      const response = await fetch(url);
      const data = await response.json() as any;

      if (!response.ok) {
        return reply.status(response.status).send(data);
      }

      const transformed = {
        ram: data.hardware?.ram ?? { total_gb: 0, used_gb: 0, available_gb: 0, usage_pct: 0 },
        swap: data.hardware?.swap ?? { used_gb: 0 },
        cpu: data.hardware?.cpu ?? { usage_pct: 0, load_avg: { '1m': 0, '5m': 0, '15m': 0 } },
        gpu_metal_usage: data.hardware?.gpu ?? null,
        llm_processes: data.hardware?.llm_processes ?? { mlx_gb: 0, embedding_gb: 0 },
      };

      return reply.send(transformed);
    } catch (error) {
      req.log.error(error as any, 'monitoring_resources_proxy_error');
      return reply.status(502).send({ error: 'Failed to connect to Me4BrAIn' });
    }
  });

  app.get('/api/monitoring/resources/history', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/monitoring/summary', req, reply);
  });

  app.get('/api/monitoring/context-tracker', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/monitoring/context-tracker', req, reply);
  });

  app.get('/api/config/llm/recommendations/hardware', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/recommendations/hardware', req, reply);
  });

  app.get('/api/config/llm/models/local', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/models/local', req, reply);
  });

  app.get('/api/config/llm/models/cloud', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/models/cloud', req, reply);
  });

  app.get('/api/config/llm/discover', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/discover', req, reply);
  });

  app.get('/api/config/llm/recommendations', async (req: FastifyRequest, reply: FastifyReply) => {
    return proxyToMe4BrAIn('/v1/config/llm/recommendations', req, reply);
  });
}
