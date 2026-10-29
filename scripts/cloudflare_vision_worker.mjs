// 整体替换现有 Jev Worker 代码，保留名为 AI 的 Workers AI 绑定。
// / 保留 Clef；/v1/chat/completions 提供读图；本地继续使用现有客户端和网关。
const MODEL = "@cf/meta/llama-3.2-11b-vision-instruct";
const headers = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function fail(message, status) {
  return Response.json({ error: { message } }, { status, headers });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers });
    }
    if (request.method !== "POST") {
      return Response.json({ error: "Only POST allowed" }, { status: 405, headers });
    }
    const path = new URL(request.url).pathname;
    if (!["/", "/v1/chat/completions", "/license"].includes(path)) {
      return fail("Use POST /, POST /v1/chat/completions or POST /license", 404);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "Invalid JSON" }, { status: 400, headers });
    }
    let model = MODEL;
    let input;
    try {
      if (path === "/") {
        // 保留原 Jev/Clef 的输入与原始返回，不经过视觉模型。
        if (!body || body.state === undefined || !body.questions) {
          return Response.json({ error: "state and questions are required" }, { status: 400, headers });
        }
        model = "@cf/cloudflare/clef";
        input = { model: "clef", state: body.state, questions: body.questions };
        if (body.images !== undefined) input.images = body.images;
      } else if (path === "/license") {
        // 只在用户主动发送 agree 时接受协议，普通读图不会自动接受。
        if (body.prompt !== "agree") {
          return fail('Read the Meta terms first, then send {"prompt":"agree"}', 400);
        }
        input = { prompt: "agree" };
      } else {
        if (body.model !== MODEL) {
          return fail(`This image endpoint only serves ${MODEL}`, 400);
        }
        if (body.stream || body.tools) {
          return fail("This image reader does not support streaming or tools", 400);
        }
        const images = [];
        const messages = body.messages.map(({ role, content }) => ({
          role,
          content: typeof content === "string" ? content : content.map(part => {
            if (part.type === "text") return part.text;
            if (part.type === "image_url") {
              images.push(part.image_url.url);
              return "";
            }
            throw new Error(`Unsupported content type: ${part.type}`);
          }).join("\n"),
        }));
        if (images.length !== 1 || !/^data:image\/(png|jpeg);base64,/.test(images[0])) {
          return fail("Send exactly one PNG/JPEG image as a base64 data URL", 400);
        }
        if (body.response_format) {
          if (body.response_format.type !== "json_object") {
            return fail("Only response_format.type=json_object is supported", 400);
          }
          // 提示约束不等于模型强制 JSON 模式；实际结构由 gateway.structured 校验。
          messages.unshift({ role: "system", content: "只返回一个符合所给结构的合法 JSON 对象，不要 Markdown 或额外说明。" });
        }
        input = {
          messages,
          image: images[0],
          max_tokens: body.max_tokens ?? 4096,
          temperature: body.temperature ?? 0,
          stream: false,
        };
      }
    } catch (error) {
      return fail(`Invalid request: ${error.message}`, 400);
    }

    let result;
    try {
      result = await env.AI.run(model, input);
    } catch (error) {
      // 上游失败明确返回错误，不伪造空读数或“成功”结果。
      if (path === "/") {
        return Response.json({ error: error.message }, { status: 502, headers });
      }
      return fail(error.message, 502);
    }
    if (path !== "/v1/chat/completions") return Response.json(result, { headers });
    if (typeof result.response !== "string" || !result.response.trim()) {
      return fail("Workers AI returned no text response", 502);
    }
    return Response.json({
      id: `chatcmpl-${crypto.randomUUID()}`,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: MODEL,
      choices: [{
        index: 0,
        message: { role: "assistant", content: result.response },
        // 原生接口未提供停止原因和 token 用量，留空而不估造。
        finish_reason: null,
      }],
    }, { headers });
  },
};
