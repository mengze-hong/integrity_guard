import fs from "node:fs";
import vm from "node:vm";

const templatePath = "app/templates/index.html";

let html;
try {
  html = fs.readFileSync(templatePath, "utf8");
} catch (error) {
  console.error(`ERROR: Failed to read ${templatePath}: ${error.message}`);
  process.exit(1);
}

const scriptPattern = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let match;
let index = 0;
let checked = 0;
let errors = 0;

while ((match = scriptPattern.exec(html)) !== null) {
  index += 1;
  const code = match[1];
  if (!code.trim()) {
    continue;
  }

  checked += 1;
  try {
    new vm.Script(code, { filename: `${templatePath}#inline-script-${index}.js` });
  } catch (error) {
    errors += 1;
    console.error(`#${index} ERROR: ${error.message}`);
  }
}

if (errors) {
  console.error(`Inline JavaScript syntax check failed: ${errors} error(s) in ${templatePath}.`);
  process.exit(1);
}

console.log(`Inline JavaScript syntax check passed: ${checked} inline script(s) in ${templatePath}.`);
