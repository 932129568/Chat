#!/usr/bin/env node
/**
 * Harbor 前端构建（零依赖，仅用 Node 内置模块）。
 *
 * 源码在 frontend/src/*.js（按文件名顺序拼接回同一个 <script>，保持 v1.0.0 单脚本作用域语义），
 * 骨架在 frontend/index.template.html；产物是项目根目录的 harbor.html
 * （pywebview 加载的文件，PyInstaller --add-data 打包的也是它）。
 *
 * 用法：node frontend/build.js
 * 规则：不要直接改根目录的 harbor.html——它是构建产物，改源码后重新构建。
 */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC_DIR = path.join(__dirname, 'src');
const TEMPLATE = path.join(__dirname, 'index.template.html');
const OUT = path.join(ROOT, 'harbor.html');
const PLACEHOLDER = '/*__APP_SCRIPT__*/';

function main() {
  const files = fs.readdirSync(SRC_DIR).filter(f => f.endsWith('.js'))
    // 按文件名前导数字自然排序（00,05,10,15,...,110），保证拼接顺序 = v1.0.0 原顺序
    .sort((a, b) => {
      const na = parseInt(a, 10), nb = parseInt(b, 10);
      if (!isNaN(na) && !isNaN(nb) && na !== nb) return na - nb;
      return a < b ? -1 : a > b ? 1 : 0;
    });
  if (!files.length) fail('frontend/src 下没有 .js 模块');
  const parts = [];
  for (const f of files) {
    const code = fs.readFileSync(path.join(SRC_DIR, f), 'utf8');
    // 修复 ㊶：模块内出现 `</script>` 字面量会提前终止内联脚本（拼进模板后 ASI/解析全乱）——逐模块拦截
    if (/<\/script/i.test(code)) fail(f + ' 含有 </script> 字面量（会提前终止内联 <script>，请拆分字符串）');
    parts.push('/* ===== ' + f + ' ===== */\n' + code.trimEnd());
  }
  const script = parts.join('\n\n');
  // 修复 ㊶：产物语法校验——new Function 编译整段拼接脚本，语法错误在构建期即失败（原只靠运行时崩）
  try {
    new Function(script);
  } catch (e) {
    fail('拼接脚本语法校验失败: ' + (e && e.message ? e.message : e));
  }
  const tpl = fs.readFileSync(TEMPLATE, 'utf8');
  // 修复 建议㊷（二轮）：占位符出现多次时原 replace 只换第一个（其余占位符原样
  // 留在产物里）——出现 >1 直接报错，逼模板保持单一注入点
  const hits = tpl.split(PLACEHOLDER).length - 1;
  if (hits !== 1) fail('模板占位符 ' + PLACEHOLDER + ' 应恰好出现 1 次，实际 ' + hits + ' 次');
  // 修复 建议㊷（二轮）：校验 libs 四个依赖文件存在（原缺文件时构建成功、
  // 运行期 marked/DOMPurify/flate 静默缺失，renderMd 直接 fail-closed 降级）
  // 修复 ㉞（三轮）：原漏检 highlight.min.js（四个 libs 只查三个）
  for (const lib of ['marked.min.js', 'purify.min.js', 'flate.js', 'highlight.min.js']) {
    if (!fs.existsSync(path.join(ROOT, 'libs', lib))) {
      fail('libs/' + lib + ' 缺失（marked/DOMPurify/flate/highlight 为运行期必需）');
    }
  }
  // 修复 ㊷（三轮）：把 VERSION 文件内容注入模板 __APP_VERSION__ 占位（原前端永无
  // APP_VERSION 定义，导出 MD 页脚恒显硬编码 '1.4'）
  let version = '';
  try { version = fs.readFileSync(path.join(ROOT, 'VERSION'), 'utf8').trim(); } catch (e) {}
  if (!version) fail('VERSION 文件缺失或为空');
  // 修复：并行修复残留的重复 const tpl 声明（L63 复读模板与 L45 冲突 → SyntaxError）
  if (tpl.split('__APP_VERSION__').length - 1 !== 1) {
    fail('模板占位符 __APP_VERSION__ 应恰好出现 1 次');
  }
  // 修复 ㉞（三轮）：String.replace 的 replacement 里 $&/$1/$$ 等序列会被特殊解释
  // （拼接脚本含正则/模板字符串时可能被静默改写）——改用函数替换，原样注入
  const html = tpl.replace(PLACEHOLDER, () => script)
                  .replace('__APP_VERSION__', () => version);
  // 原重复 </script> 检查升级为上面的逐模块检查 + 语法校验，保留产物输出
  fs.writeFileSync(OUT, html, 'utf8');
  console.log('[build] %d 个模块 -> %s (%d 行)',
    files.length, path.relative(ROOT, OUT), html.split('\n').length);
}

function fail(msg) { console.error('[build] 失败: ' + msg); process.exit(1); }

main();
