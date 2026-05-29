import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

const helperCode = fs.readFileSync("app/static/js/helpers.js", "utf8");

function loadHelpers() {
  const context = vm.createContext({});
  vm.runInContext(helperCode, context, { filename: "app/static/js/helpers.js" });
  return context;
}

function sameRealm(value) {
  return JSON.parse(JSON.stringify(value));
}

test("jsArg returns JSON string literals for inline handlers", () => {
  const { jsArg } = loadHelpers();

  assert.equal(jsArg('a"b'), JSON.stringify('a"b'));
  assert.equal(jsArg("a\\b"), JSON.stringify("a\\b"));
  assert.equal(jsArg("a\nb"), JSON.stringify("a\nb"));
  assert.equal(jsArg(null), JSON.stringify(""));
});

test("esc performs deterministic HTML escaping", () => {
  const { esc } = loadHelpers();

  assert.equal(
    esc(`<script>&"'</script>`),
    "&lt;script&gt;&amp;&quot;&#39;&lt;/script&gt;",
  );
});

test("canAiSuggestFix blocks reference authenticity and reference patterns", () => {
  const { canAiSuggestFix, REF_AUTH_ISSUE_PATTERNS } = loadHelpers();

  assert.ok(REF_AUTH_ISSUE_PATTERNS.includes("缺少 DOI"));
  assert.equal(canAiSuggestFix("reference_authenticity", "any issue"), false);
  assert.equal(canAiSuggestFix("writing_quality", "缺少 DOI，需要核实"), false);
  assert.equal(canAiSuggestFix("writing_quality", "Unverified reference in bibliography"), false);
  assert.equal(canAiSuggestFix("writing_quality", "Sentence is too long"), true);
});

test("normEol and stripFences normalize helper text", () => {
  const { normEol, stripFences } = loadHelpers();

  assert.equal(normEol("a\r\nb\rc"), "a\nb\nc");
  assert.equal(stripFences("```latex\nhello\n```"), "hello");
  assert.equal(stripFences("  ```\nhello\n```  "), "hello");
  assert.equal(stripFences("plain text"), "plain text");
});

test("groupFixesByGate preserves original indexes", () => {
  const { groupFixesByGate } = loadHelpers();
  const fixes = [
    { gate_name: "writing_quality", message: "one" },
    { gate_name: "data_integrity", message: "two" },
    { message: "three" },
  ];

  const grouped = groupFixesByGate(fixes);

  assert.deepEqual(sameRealm(grouped.writing_quality), [
    { gate_name: "writing_quality", message: "one", _idx: 0 },
  ]);
  assert.deepEqual(sameRealm(grouped.data_integrity), [
    { gate_name: "data_integrity", message: "two", _idx: 1 },
  ]);
  assert.deepEqual(sameRealm(grouped.unknown), [{ message: "three", _idx: 2 }]);
});

test("indexesForGate returns matching fix indexes", () => {
  const { indexesForGate } = loadHelpers();
  const fixes = [
    { gate_name: "writing_quality" },
    { gate_name: "data_integrity" },
    { gate_name: "writing_quality" },
    {},
  ];

  assert.deepEqual(indexesForGate(fixes, "writing_quality"), [0, 2]);
  assert.deepEqual(indexesForGate(fixes, "unknown"), [3]);
  assert.deepEqual(indexesForGate(fixes, "missing"), []);
});

test("prepareFixText and replaceOnce normalize and replace safely", () => {
  const { prepareFixText, replaceOnce } = loadHelpers();
  const fix = {
    original: "alpha\r\n$1\r\nomega",
    fixed: "```tex\nalpha\r\n$1 fixed\r\nomega\n```",
  };

  const prepared = prepareFixText(fix);

  assert.deepEqual(sameRealm(prepared), {
    original: "alpha\n$1\nomega",
    fixed: "alpha\n$1 fixed\nomega",
  });

  const updated = replaceOnce(
    "before\r\nalpha\r\n$1\r\nomega\r\nmiddle\r\nalpha\r\n$1\r\nomega",
    prepared.original,
    prepared.fixed,
  );

  assert.equal(
    updated,
    "before\nalpha\n$1 fixed\nomega\nmiddle\nalpha\n$1\nomega",
  );
  assert.equal(replaceOnce("unchanged", "missing", "replacement"), null);
});
