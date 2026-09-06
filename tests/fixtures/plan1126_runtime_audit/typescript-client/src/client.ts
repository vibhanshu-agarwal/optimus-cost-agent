import * as acp from "@agentclientprotocol/sdk";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { Readable, Writable } from "node:stream";
import { fileURLToPath } from "node:url";

const METHOD_RESULTS: string[] = [];

async function main(): Promise<void> {
  const fixturePath = join(dirname(fileURLToPath(import.meta.url)), "../../fixture_agent.py");
  const fixture = spawn(process.env.PYTHON ?? "python", [fixturePath], {
    stdio: ["pipe", "pipe", "pipe"],
  });
  if (fixture.stdin === null || fixture.stdout === null) {
    throw new Error("fixture stdio unavailable");
  }

  const input = Writable.toWeb(fixture.stdin) as unknown as WritableStream<Uint8Array>;
  const output = Readable.toWeb(fixture.stdout) as unknown as ReadableStream<Uint8Array>;
  const stream = acp.ndJsonStream(input, output);
  try {
    await acp.client({ name: "plan1126-sdk-qualification" }).connectWith(stream, async (ctx) => {
      await ctx.request(acp.methods.agent.initialize, {
        protocolVersion: acp.PROTOCOL_VERSION,
        clientCapabilities: {},
      });
      METHOD_RESULTS.push("initialize:success");

      const session = await ctx.buildSession(process.cwd()).start();
      METHOD_RESULTS.push("session/new:success");
      try {
        await session.prompt("qualification");
        METHOD_RESULTS.push("session/prompt:success");
      } finally {
        session.dispose();
        await ctx.request(acp.methods.agent.session.close, { sessionId: session.sessionId });
        METHOD_RESULTS.push("session/close:success");
      }
    });
    process.stdout.write(`${JSON.stringify({ observed_method_results: METHOD_RESULTS })}\n`);
  } finally {
    fixture.kill();
  }
}

void main().catch(() => {
  process.stderr.write("qualification failed\n");
  process.exitCode = 1;
});
