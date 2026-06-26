import { spawnSync } from "node:child_process";
import fs from "node:fs";

const selfPath = "scripts/secret-scan.mjs";
// Files that legitimately define or test secret-handling patterns. They have
// no real secrets but carry pattern literals (e.g. sk-uin… prefixes,
// LLM_BASE_URL=__paste_here__ in deployment docs) that would otherwise
// trigger this scan.
const excludedPaths = new Set([
  selfPath,
  "app/secrets_manager.py",
  "tests/test_redact.py",
  ".env.example",
  "docs/DEPLOY_TENCENT.md",
]);

const excludedPrefixes = [
  ".cursor/",
  ".workbuddy/",
  ".git/",
  "_Archive/",
  "uploads/",
];

const placeholderValue =
  String.raw`(?:$|["']?\s*$|<|example|changeme|dummy|test|admintest|none|null|os\.getenv|process\.env|get_secret|get_or_create_secret|settings\.|[_A-Za-z][A-Za-z0-9_]*\(|\$\{?)`;
const tunnelProviderPrefix = "CLOUD" + "FLARE";

function assignmentPattern(namePattern, minLength = 8) {
  return new RegExp(
    String.raw`\b${namePattern}\b\s*[:=]\s*["']?(?!\s*${placeholderValue})[A-Za-z0-9_./+=:@-]{${minLength},}`,
    "i",
  );
}

const patterns = [
  {
    name: "internal LLM API key prefix",
    regex: /\bsk-(?:uin|TpK)[A-Za-z0-9_-]*/i,
  },
  {
    name: "internal endpoint host",
    regex: /\b(?:woa\.com|sgpolaris)\b/i,
  },
  {
    name: "Bearer OpenAI-style key",
    regex: /\bBearer\s+sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}/i,
  },
  {
    name: "LLM API key assignment",
    regex: assignmentPattern(
      String.raw`(?:LLM|OPENAI|ANTHROPIC|GEMINI|DEEPSEEK|DASHSCOPE|KIMI|MOONSHOT)_[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET)`,
    ),
  },
  {
    name: "LLM base URL assignment",
    regex: assignmentPattern(
      String.raw`(?:LLM|OPENAI|ANTHROPIC|GEMINI|DEEPSEEK|DASHSCOPE|KIMI|MOONSHOT)_[A-Z0-9_]*BASE_URL`,
    ),
  },
  {
    name: "tunnel provider token/key assignment",
    regex: assignmentPattern(
      String.raw`(?:${tunnelProviderPrefix}|CF)_[A-Z0-9_]*(?:TOKEN|KEY|SECRET|GLOBAL_API_KEY|API_TOKEN|API_KEY)`,
    ),
  },
  {
    name: "JWT secret/key assignment",
    regex: assignmentPattern(String.raw`JWT_[A-Z0-9_]*(?:SECRET|KEY)`, 12),
  },
  {
    name: "admin secret/password/key assignment",
    regex: assignmentPattern(
      String.raw`(?:ADMIN_[A-Z0-9_]*(?:SECRET|PASSWORD|PASS|KEY|TOKEN)|admin_(?:secret|password|key|token))`,
      8,
    ),
  },
  {
    name: "payment provider secret/key assignment",
    regex: assignmentPattern(
      String.raw`(?:(?:PAYMENT|STRIPE)_[A-Z0-9_]*(?:SECRET|KEY|TOKEN|WEBHOOK_SECRET)|(?:ALIPAY|WECHATPAY|WECHAT|WX)_[A-Z0-9_]*(?:SECRET|KEY|TOKEN|PRIVATE_KEY|MCH_KEY|API_KEY|V3_KEY)|(?:stripe|payment|alipay|wechatpay|wechat|wx)_(?:secret|key|token|private_key|mch_key|api_key|v3_key))`,
      8,
    ),
  },
  {
    name: "Stripe live secret key",
    regex: /\b(?:sk_live|rk_live)_[A-Za-z0-9]{16,}\b/i,
  },
  {
    name: "private key block",
    regex: /-----BEGIN [^-]*PRIVATE KEY-----/i,
  },
];

function normalizePath(path) {
  return path.replaceAll("\\", "/");
}

function isExcluded(path) {
  const normalized = normalizePath(path);
  return (
    excludedPaths.has(normalized) ||
    excludedPrefixes.some((prefix) => normalized.startsWith(prefix))
  );
}

function isBinary(buffer) {
  return buffer.includes(0);
}

function redact(line) {
  return line
    .replace(/\bBearer\s+sk-[A-Za-z0-9_-]+/gi, "Bearer sk-***")
    .replace(/\bsk-(?:uin|TpK)[A-Za-z0-9_-]*/gi, "sk-***")
    .replace(
      /(\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASS|KEY|BASE_URL)\b\s*[:=]\s*["']?)[^"'\s#]+/gi,
      "$1***",
    )
    .replace(
      /(\b(?:admin|stripe|payment|alipay|wechatpay|wechat|wx)_(?:secret|password|pass|key|token|private_key|mch_key|api_key|v3_key)\b\s*[:=]\s*["']?)[^"'\s#]+/gi,
      "$1***",
    );
}

const listed = spawnSync(
  "git",
  ["-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
);

if (listed.status !== 0) {
  console.error(listed.stderr || "Failed to list repository files for secret scan.");
  process.exit(listed.status || 1);
}

const files = listed.stdout
  .toString("utf8")
  .split("\0")
  .filter(Boolean)
  .filter((file) => !isExcluded(file));

const findings = [];

for (const file of files) {
  let buffer;
  try {
    buffer = fs.readFileSync(file);
  } catch (error) {
    findings.push({
      file,
      lineNumber: 0,
      name: "unreadable file",
      line: `ERROR: ${error.message}`,
    });
    continue;
  }

  if (isBinary(buffer)) {
    continue;
  }

  const lines = buffer.toString("utf8").split(/\r?\n/);
  lines.forEach((line, index) => {
    for (const pattern of patterns) {
      if (pattern.regex.test(line)) {
        findings.push({
          file,
          lineNumber: index + 1,
          name: pattern.name,
          line: redact(line.trim()),
        });
      }
    }
  });
}

if (findings.length > 0) {
  console.error("Sensitive internal secret or endpoint pattern found:");
  for (const finding of findings) {
    console.error(`${finding.file}:${finding.lineNumber}: ${finding.name}: ${finding.line}`);
  }
  process.exit(1);
}

console.log(`Secret scan passed: checked ${files.length} repository file(s).`);
