(function attachHelpers(global) {
    'use strict';

    const REF_AUTH_ISSUE_PATTERNS = [
        'DOI 无法解析', '缺少 DOI', '无可信来源', '标题搜索未找到',
        '无法验证', '伪造', '撤稿', 'Unverified reference', 'source not found',
        'DOI/source not found', 'official URL/DOI'
    ];

    function esc(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Produces a JS string literal safe to embed inside a DOUBLE-quoted
    // inline attribute (onclick="fn(${jsArg(x)})"). JSON.stringify gives a
    // "..."-wrapped literal; HTML-escaping it turns the wrapping quotes into
    // &quot; so they don't prematurely close the attribute — the browser
    // decodes them back to real quotes before compiling the handler.
    function jsArg(value) {
        return esc(JSON.stringify(String(value ?? '')));
    }

    function normEol(value) {
        return String(value ?? '').replace(/\r\n?/g, '\n');
    }

    function stripFences(value) {
        let text = String(value ?? '').trim();
        if (text.startsWith('```')) {
            text = text.replace(/^```[^\n]*\n/, '').replace(/\n?```\s*$/, '');
        }
        return text;
    }

    function canAiSuggestFix(gateName, message) {
        if (gateName === 'reference_authenticity') return false;
        const msg = String(message ?? '');
        return !REF_AUTH_ISSUE_PATTERNS.some(pattern => msg.includes(pattern));
    }

    function groupFixesByGate(fixes) {
        return (Array.isArray(fixes) ? fixes : []).reduce((acc, fix, index) => {
            const item = fix || {};
            const gate = item.gate_name || 'unknown';
            (acc[gate] ||= []).push({...item, _idx: index});
            return acc;
        }, {});
    }

    function indexesForGate(fixes, gateName) {
        return (Array.isArray(fixes) ? fixes : [])
            .map((fix, index) => ({fix: fix || {}, index}))
            .filter(({fix}) => (fix.gate_name || 'unknown') === gateName)
            .map(({index}) => index);
    }

    function prepareFixText(fix) {
        return {
            original: normEol(fix?.original),
            fixed: stripFences(normEol(fix?.fixed)),
        };
    }

    function replaceOnce(content, original, fixed) {
        const normalizedContent = normEol(content);
        const normalizedOriginal = normEol(original);
        const preparedFixed = stripFences(normEol(fixed));
        if (!normalizedOriginal || !normalizedContent.includes(normalizedOriginal)) return null;
        return normalizedContent.replace(normalizedOriginal, () => preparedFixed);
    }

    Object.assign(global, {
        REF_AUTH_ISSUE_PATTERNS,
        jsArg,
        esc,
        normEol,
        stripFences,
        canAiSuggestFix,
        groupFixesByGate,
        indexesForGate,
        prepareFixText,
        replaceOnce,
    });
})(globalThis);
