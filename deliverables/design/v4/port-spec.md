# GLM-Chat v4 UI 重设计 · 代码落地规格书（ui-porter 执行依据）

> 本文件是《GLM-Chat v4 设计令牌文档》（彩格调）到真实代码库的落地映射。执行者逐节替换，不重写架构。

## 0. 执行铁律

1. 只改 `frontend/index.template.html` 的 `<style>` 块 + 本规格第 3 节列出的 JS 模块。**绝不手改根目录 glm-chat.html**。
2. v2 令牌（见第 1 节清单）名字与值一字不改。
3. 39 个契约 CSS 类必须仍在模板样式段出现（值可改）。
4. 改完执行：`node frontend/build.js`（成功）+ `python deliverables/design/check_contract.py`（PASS）+ `pytest tests/test_review_fixes.py tests/test_v13_qa.py -q`（全绿）。
5. 零第三方依赖；JS 硬编码动效时长清零（走 `frontend/src/00-motion.js` 的 MOTION，已就位）。
6. 代码风格：中文注释、`/* ===== 标题 ===== */` 分节、「修复 XX：」注释格式，与现有一致。

## 1. v4 CSS 变量块（整体替换现有 :root 与 body.dark 两个块）

```css
:root{
  /* ===== v2 保留（值不变，禁止删改）===== */
  --bg:#f6f7f9; --sidebar-bg:#ffffff; --main-bg:#f6f7f9; --header-bg:rgba(255,255,255,.78);
  --card-bg:#ffffff; --surface-2:#f1f3f7;
  --border:#e4e6ec; --border-strong:#d2d6e0;
  --text:#14161c; --text-2:#5f6674; --text-3:#6a7180;
  --primary:#4f6ef7; --primary-hover:#3d5ae6; --primary-soft:#eef1fe;
  --user-bubble:#4059e0; --user-bubble-text:#ffffff; --ai-bubble:#ffffff;
  --hover:#f1f3f7; --active:#eef1fe; --chip-bg:#f1f3f7;
  --ok:#1a7f4e; --warn:#b7791f; --err:#cf3222;
  --ok-bg:#e8f6ee; --warn-bg:#fdf5e6; --err-bg:#fdecea;
  --shadow-sm:0 1px 2px rgba(16,18,28,.06);
  --shadow-md:0 2px 8px rgba(16,18,28,.08);
  --shadow-lg:0 12px 28px rgba(16,18,28,.14);
  --radius-xs:4px; --radius-sm:6px; --radius-md:9px; --radius-lg:12px; --radius-xl:16px; --radius-full:999px;
  --font-sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;
  --font-mono:"JetBrains Mono","Cascadia Code",Consolas,"SFMono-Regular",Menlo,monospace;
  --dur-fast:120ms; --dur-base:180ms; --dur-slow:280ms;
  --ease:cubic-bezier(.4,0,.2,1); --ease-out:cubic-bezier(.16,1,.3,1);
  --sidebar-w:264px; --content-w:820px;
  --brand-gradient:linear-gradient(135deg,#6b84ff,#4f6ef7);

  /* ===== v4 玻璃层（值保留 v3）===== */
  --glass-bg:rgba(255,255,255,.62);
  --glass-bg-2:rgba(255,255,255,.80);
  --glass-border:rgba(255,255,255,.72);
  --glass-blur:18px;
  --glass-fallback:#f4f6fb;
  --glass-saturate:1.15;

  /* ===== v4 极光（2 光斑 · 青/紫 · 品红退役 · 纯 translate）===== */
  --aurora-1:#22d3ee;
  --aurora-2:#4f6ef7;
  --aurora-3:#8b5cf6;
  --aurora-4:#ec4899;
  --aurora-opacity:.12;
  --aurora-bg-opacity:.50;
  --aurora-blur:64px;

  /* ===== v4 发光（值保留 v3；收紧在使用范围）===== */
  --glow-color:rgba(79,110,247,.50);
  --glow:0 0 0 1px var(--glass-border),0 0 22px -6px var(--glow-color);
  --glow-strong:0 0 0 1px rgba(79,110,247,.60),0 0 34px -4px rgba(79,110,247,.70);
  --glow-focus:0 0 0 3px var(--primary-soft),0 0 20px -4px var(--glow-color);
  --brand-glow:radial-gradient(circle at 30% 30%,var(--glow-color),transparent 70%);

  /* ===== v4 图表色板（品红仅存在于 --chart-4）===== */
  --chart-1:#4f6ef7; --chart-2:#22d3ee; --chart-3:#8b5cf6; --chart-4:#ec4899;
  --chart-grid:rgba(16,18,28,.08); --chart-axis:#6a7180;
  --chart-area-from:rgba(79,110,247,.26); --chart-area-to:rgba(79,110,247,0);

  /* ===== v4 动效时长 · 四层模型 ===== */
  --dur-press:90ms;
  --dur-micro:130ms;
  --dur-micro-out:90ms;
  --dur-comp:200ms;
  --dur-comp-out:140ms;
  --dur-panel:240ms;
  --dur-panel-out:200ms;
  --dur-narr:220ms;
  --dur-theme:280ms;
  --dur-count:600ms;
  --dur-chart:800ms;
  --dur-ambient:34s;
  --dur-ambient-2:52s;
  --dur-sheen:6s;
  --dur-breathe:2.6s;
  --dur-stream:1.4s;

  /* ===== v4 动效缓动 ===== */
  --ease-out-soft:cubic-bezier(.25,.8,.35,1);
  --ease-in-soft:cubic-bezier(.42,0,1,1);
  --ease-spring:cubic-bezier(.34,1.3,.5,1);
  --ease-glow:var(--ease-out-soft);

  /* ===== v4 编排令牌 ===== */
  --stagger-xs:40ms;
  --stagger-sm:60ms;

  /* ===== v4 位移令牌 ===== */
  --shift-tip:4px;
  --shift-comp:6px;
  --shift-toast:8px;
  --shift-msg:8px;
  --shift-panel:12px;

  /* ===== v4 兼容别名（旧名 → 新令牌；新代码禁用旧名）===== */
  --dur-glow:var(--dur-micro);
  --dur-aurora:var(--dur-ambient);
  --dur-aurora-2:var(--dur-ambient-2);

  /* ===== v4 导航与面板尺寸（v3 值保留）===== */
  --rail-w:60px; --rail-btn:40px; --rail-gap:6px;
  --panel-pad:22px; --panel-gap:16px; --panel-title:18px;
  --chart-h:240px; --chart-h-sm:160px;
  --main-veil:rgba(246,247,249,.88);
}
body.dark{
  /* ===== v2 保留（值不变，禁止删改）===== */
  --bg:#101114; --sidebar-bg:#16181d; --main-bg:#101114; --header-bg:rgba(22,24,29,.78);
  --card-bg:#1a1c22; --surface-2:#212429;
  --border:#272a32; --border-strong:#343843;
  --text:#e6e7ea; --text-2:#8b909c; --text-3:#9298a6;
  --primary:#6b84ff; --primary-hover:#8098ff; --primary-soft:#1d2337;
  --user-bubble:#3b53c9; --user-bubble-text:#ffffff; --ai-bubble:#1a1c22;
  --hover:#212429; --active:#232a3f; --chip-bg:#212429;
  --ok:#4ade80; --warn:#fbbf24; --err:#f87171;
  --ok-bg:#12251b; --warn-bg:#2a2213; --err-bg:#2b1618;
  --shadow-sm:0 1px 2px rgba(0,0,0,.4);
  --shadow-md:0 2px 10px rgba(0,0,0,.45);
  --shadow-lg:0 16px 40px rgba(0,0,0,.6);

  /* ===== v4 玻璃层（深色）===== */
  --glass-bg:rgba(26,28,34,.60);
  --glass-bg-2:rgba(30,33,41,.78);
  --glass-border:rgba(255,255,255,.10);
  --glass-blur:20px;
  --glass-fallback:#171a21;
  --glass-saturate:1.15;

  /* ===== v4 极光（深色同色相）===== */
  --aurora-1:#22d3ee; --aurora-2:#6b84ff; --aurora-3:#8b5cf6; --aurora-4:#ec4899;
  --aurora-opacity:.12; --aurora-bg-opacity:.55; --aurora-blur:64px;

  /* ===== v4 发光（深色）===== */
  --glow-color:rgba(107,132,255,.55);
  --glow:0 0 0 1px var(--glass-border),0 0 22px -6px var(--glow-color);
  --glow-strong:0 0 0 1px rgba(107,132,255,.65),0 0 34px -4px rgba(107,132,255,.75);
  --glow-focus:0 0 0 3px var(--primary-soft),0 0 20px -4px var(--glow-color);
  --brand-glow:radial-gradient(circle at 30% 30%,var(--glow-color),transparent 70%);

  /* ===== v4 图表色板（深色）===== */
  --chart-1:#6b84ff; --chart-2:#34e0f5; --chart-3:#a78bfa; --chart-4:#f472b6;
  --chart-grid:rgba(255,255,255,.09); --chart-axis:#8b909c;
  --chart-area-from:rgba(107,132,255,.30); --chart-area-to:rgba(107,132,255,0);

  --main-veil:rgba(16,17,20,.88);
}
```

## 2. 模板 CSS 逐项替换（index.template.html <style> 块）

### 2.1 极光（替换现有 E1 整块：.au-1/.au-2/.au-3 + @keyframes auroraA/auroraB）
```css
/* ===== v4 E1 · 极光背景层（fixed，z-index:-1，双周期纯 translate 漂移）===== */
#auroraBg{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none;
  opacity:var(--aurora-bg-opacity);background:var(--bg);}
#auroraBg .au{position:absolute;width:58vmax;height:58vmax;border-radius:50%;
  filter:blur(var(--aurora-blur));will-change:transform;}
#auroraBg .au-1{top:-20vmax;left:-14vmax;opacity:.66;
  background:radial-gradient(circle at 50% 50%,var(--aurora-1),transparent 62%);
  animation:v4AuroraA var(--dur-ambient) ease-in-out infinite alternate;}
#auroraBg .au-2{bottom:-22vmax;right:-16vmax;opacity:.62;
  background:radial-gradient(circle at 50% 50%,var(--aurora-3),transparent 62%);
  animation:v4AuroraB var(--dur-ambient-2) ease-in-out infinite alternate;}
#auroraBg .au-3{display:none;}   /* 品红光斑退役（DOM 节点保留不删） */
@keyframes v4AuroraA{from{transform:translate3d(0,0,0)}to{transform:translate3d(8vmax,5vmax,0)}}
@keyframes v4AuroraB{from{transform:translate3d(0,0,0)}to{transform:translate3d(-7vmax,-6vmax,0)}}
```

### 2.2 流式条（替换 .stream-bar/.stream-bar.on/@keyframes indeterminate）
```css
.stream-bar{position:fixed;top:0;left:0;height:2px;width:32%;z-index:10000;
  background:var(--primary);border-radius:0 var(--radius-full) var(--radius-full) 0;
  box-shadow:0 0 12px 0 var(--glow-color);
  transform:translateX(-100%);opacity:0;
  transition:opacity var(--dur-micro) var(--ease-out-soft);}
.stream-bar.on{opacity:1;will-change:transform,opacity;
  animation:v4Stream var(--dur-stream) ease-in-out infinite;}
@keyframes v4Stream{from{transform:translateX(-100%)}to{transform:translateX(100vw)}}
```

### 2.3 面板切换（替换 .panel.on 的 animation:panelIn 与 @keyframes panelIn）
```css
.panel{display:none;flex:1;min-width:0;min-height:0;flex-direction:column;}
.panel.on{display:flex;}
.panel.leaving{position:absolute;inset:0;z-index:0;pointer-events:none;}
.panel.in-fwd,.panel.in-back{position:relative;z-index:1;}
.panel.in-fwd{animation:v4PanelInFwd var(--dur-panel) var(--ease-out);}
.panel.in-back{animation:v4PanelInBack var(--dur-panel) var(--ease-out);}
.panel.out-fwd{animation:v4PanelOutFwd var(--dur-panel-out) var(--ease-in-soft) forwards;}
.panel.out-back{animation:v4PanelOutBack var(--dur-panel-out) var(--ease-in-soft) forwards;}
@keyframes v4PanelInFwd{from{opacity:0;transform:translateX(var(--shift-panel))}to{opacity:1;transform:none}}
@keyframes v4PanelInBack{from{opacity:0;transform:translateX(calc(-1*var(--shift-panel)))}to{opacity:1;transform:none}}
@keyframes v4PanelOutFwd{from{opacity:1;transform:none}to{opacity:0;transform:translateX(calc(-1*var(--shift-panel)))}}
@keyframes v4PanelOutBack{from{opacity:1;transform:none}to{opacity:0;transform:translateX(var(--shift-panel))}}
body.fx-off .panel{animation:none!important;}
```
注意：现有 `.panel` 规则里除 animation 外的属性保留；只把 `.panel.on{display:flex;animation:panelIn...}` 的 animation 部分去掉，并删除 @keyframes panelIn。

### 2.4 消息流（替换 .message 的 animation:fadeInUp .22s 与 @keyframes fadeInUp）
```css
.message{margin-bottom:20px;display:flex;gap:11px;animation:v4MsgIn var(--dur-narr) var(--ease-out-soft);}
@keyframes v4MsgIn{from{opacity:0;transform:translateY(var(--shift-msg))}to{opacity:1;transform:none}}
.empty-state{text-align:center;padding:100px 20px;color:var(--text-3);animation:v4MsgIn var(--dur-narr) var(--ease-out-soft);}
.chat-container.batch .message,.chat-container.batch .empty-state{animation:none;}
.chat-container{transition:opacity var(--dur-comp) var(--ease-out-soft);}
.chat-container.swapping{opacity:0;transition:opacity var(--dur-comp-out) var(--ease-in-soft);}
.msg-images img{transition:transform var(--dur-micro) var(--ease-out-soft);}
```
`.attach-preview.show`/`.toast`/`.modal-card` 的 fadeInUp 引用按 2.9/2.10/2.11 换成各自 keyframes；全部替换完且 grep 无残留后才删 @keyframes fadeInUp（有残留则保留定义）。

### 2.5 工具卡三态（替换 toolPulse/done/fail/toolSheen 相关规则）
```css
.tool-call-item{position:relative;overflow:hidden;
  transition:border-color var(--dur-comp) var(--ease-out-soft),
             background-color var(--dur-comp) var(--ease-out-soft),
             color var(--dur-comp) var(--ease-out-soft);
  animation:v4ToolBreathe var(--dur-breathe) ease-in-out infinite;}
@keyframes v4ToolBreathe{0%,100%{opacity:.88}50%{opacity:1}}
.tool-call-item .tc-dot{transition:background-color var(--dur-comp) var(--ease-out-soft);}
.tool-call-item.done{border-left-color:var(--ok);color:var(--text-2);animation:v4ToolSettle var(--dur-comp) var(--ease-out-soft);}
@keyframes v4ToolSettle{0%{box-shadow:0 0 0 1px var(--ok),0 0 14px -4px var(--ok)}100%{box-shadow:0 0 0 1px transparent,0 0 0 0 transparent}}
.tool-call-item.fail{border-left-color:var(--err);background:var(--err-bg);color:var(--err);animation:none;}
body:not(.fx-off) .tool-call-item:not(.done):not(.fail)::after{content:"";position:absolute;inset:0;
  background:linear-gradient(105deg,transparent 42%,rgba(255,255,255,.26) 50%,transparent 58%);
  transform:translateX(-100%);animation:toolSheen var(--dur-sheen) linear infinite;pointer-events:none;}
@keyframes toolSheen{to{transform:translateX(100%)}}
```

### 2.6 自定义下拉（替换 .cs.open .cs-menu 的 slideDown 与 @keyframes slideDown 的CS部分）
```css
.cs-arrow{transition:transform var(--dur-micro) var(--ease-out-soft);}
.cs.open .cs-arrow{transform:rotate(180deg);}
.cs.open .cs-menu{display:block;transform-origin:top center;
  animation:v4CsIn var(--dur-comp) var(--ease-out-soft);}
@keyframes v4CsIn{from{opacity:0;transform:translateY(calc(-1*var(--shift-comp))) scale(.98)}to{opacity:1;transform:none}}
.cs.open.hiding .cs-menu{animation:v4CsOut var(--dur-comp-out) var(--ease-in-soft) forwards;}
@keyframes v4CsOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(calc(-1*var(--shift-comp))) scale(.98)}}
```

### 2.7 设置浮层（替换 .settings-panel.show 的 slideDown）
```css
.settings-panel.show{display:block;animation:v4SetIn var(--dur-comp) var(--ease-out-soft);}
@keyframes v4SetIn{from{opacity:0;transform:translateY(calc(-1*var(--shift-comp)))}to{opacity:1;transform:none}}
.settings-panel.show.hiding{animation:v4SetOut var(--dur-comp-out) var(--ease-in-soft) forwards;}
@keyframes v4SetOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(calc(-1*var(--shift-comp)))}}
```

### 2.8 tooltip（替换 tipIn）
```css
.rail-btn::after{transition:opacity var(--dur-micro) var(--ease-out-soft),transform var(--dur-micro) var(--ease-out-soft);}
@keyframes v4TipIn{from{opacity:0;transform:translateX(calc(-1*var(--shift-tip)))}to{opacity:1;transform:none}}
```
（找到现有 tooltip 规则：把动画/过渡换成 130ms ease-out-soft + --shift-tip；tipIn 若无其他引用可删。）

### 2.9 toast（替换 .toast 的 fadeInUp .18s 与退场规则）
```css
.toast{font-size:12.5px;color:var(--text);animation:v4ToastIn var(--dur-comp) var(--ease-out-soft);word-break:break-all;}
@keyframes v4ToastIn{from{opacity:0;transform:translateX(var(--shift-toast))}to{opacity:1;transform:none}}
.toast.out{animation:none;opacity:0;transform:translateX(var(--shift-toast));
  transition:opacity var(--dur-comp-out) var(--ease-in-soft),transform var(--dur-comp-out) var(--ease-in-soft);}
```

### 2.10 模态（替换 .modal-card 的 fadeInUp .18s；新增遮罩与退场）
```css
.modal-mask{animation:v4MaskIn var(--dur-comp) var(--ease-out-soft);}
@keyframes v4MaskIn{from{opacity:0}to{opacity:1}}
.modal-card{box-shadow:var(--shadow-lg);padding:18px 18px 14px;animation:v4ModalIn var(--dur-comp) var(--ease-spring);}
@keyframes v4ModalIn{from{opacity:0;transform:translate(-50%,-50%) scale(.96)}to{opacity:1;transform:translate(-50%,-50%) scale(1)}}
#modalRoot.closing .modal-mask{animation:none;opacity:0;transition:opacity var(--dur-comp-out) var(--ease-in-soft);}
#modalRoot.closing .modal-card{animation:v4ModalOut var(--dur-comp-out) var(--ease-in-soft) forwards;}
@keyframes v4ModalOut{from{opacity:1;transform:translate(-50%,-50%) scale(1)}to{opacity:0;transform:translate(-50%,-50%) scale(.96)}}
```
⚠ .modal-card 定位是 left:50%;top:38%;transform:translate(-50%,-50%)——keyframes 必须携带 translate(-50%,-50%)，否则居中失效。

### 2.11 右键菜单（.ctx-menu 现有 display 瞬切 → v4）
```css
.ctx-menu{transform-origin:top left;}
.ctx-menu.show{display:block;animation:v4CtxIn var(--dur-comp) var(--ease-out-soft);}
@keyframes v4CtxIn{from{opacity:0;transform:scale(.97) translateY(calc(-1*var(--shift-comp)))}to{opacity:1;transform:none}}
.ctx-menu.show.hiding{animation:v4CtxOut var(--dur-comp-out) var(--ease-in-soft) forwards;}
@keyframes v4CtxOut{from{opacity:1;transform:none}to{opacity:0;transform:scale(.97) translateY(calc(-1*var(--shift-comp)))}}
.ctx-menu.show .ctx-menu-item{animation:v4CtxItemIn var(--dur-comp) var(--ease-out-soft) backwards;}
.ctx-menu.show .ctx-menu-item:nth-child(2){animation-delay:var(--stagger-xs)}
.ctx-menu.show .ctx-menu-item:nth-child(3){animation-delay:calc(var(--stagger-xs)*2)}
.ctx-menu.show .ctx-menu-item:nth-child(4){animation-delay:calc(var(--stagger-xs)*3)}
@keyframes v4CtxItemIn{from{opacity:0;transform:translateY(-2px)}to{opacity:1;transform:none}}
```

### 2.12 附件条（替换 .attach-preview.show 的 fadeInUp .2s）
```css
.attach-preview.show{display:flex;animation:v4AttachIn var(--dur-comp) var(--ease-out-soft);}
@keyframes v4AttachIn{from{opacity:0;transform:translateY(var(--shift-comp))}to{opacity:1;transform:none}}
.attach-preview.show.hiding{animation:v4AttachOut var(--dur-comp-out) var(--ease-in-soft) forwards;}
@keyframes v4AttachOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(var(--shift-comp))}}
.attach-item.enter{animation:v4AttachItemIn var(--dur-comp) var(--ease-out-soft);}
@keyframes v4AttachItemIn{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:none}}
.attach-item .remove{transition:transform var(--dur-micro) var(--ease-out-soft),background-color var(--dur-micro) var(--ease-out-soft);}
```

### 2.13 会话行竖条（.session-item::before 现有 height 过渡 → scaleY）
找到现有规则（约 L288-293，height:0→18px 过渡）替换为：
```css
.session-item::before{content:"";position:absolute;left:0;top:50%;width:3px;height:18px;
  border-radius:var(--radius-full);background:var(--primary);
  transform:translateY(-50%) scaleY(0);transform-origin:center;
  transition:transform var(--dur-comp) var(--ease-out-soft);}
.session-item.on::before{transform:translateY(-50%) scaleY(1);}
```
（颜色/尺寸以现有规则为准微调，语义不变；若现有结构不同，保持「选中=可见竖条」语义换成 scaleY 实现。）

### 2.14 按钮家族统一（消灭三档速率 + 补 :active + :focus-visible）
把散落的 hover transition（120ms 只变背景 / 120ms+260ms 发光 / 180ms 图片等）统一。新增：
```css
.rail-btn,.icon-btn,.pill-btn,.ghost-btn,.ws-btn,.seg-btn,.tool-btn,.send-btn,
.new-chat-btn,.copy-btn,.code-copy,.set-nav-btn,.modal-btn,.pause-btn,.audit-chip,
.session-del,.session-exp,.attach-item .remove,.toast-close,.toast-more,#continueNewBtn,
.ctx-menu-item,.cs-opt,.search-hit{
  transition:background-color var(--dur-micro) var(--ease-out-soft),
             color var(--dur-micro) var(--ease-out-soft),
             border-color var(--dur-micro) var(--ease-out-soft),
             box-shadow var(--dur-micro) var(--ease-out-soft),
             transform var(--dur-press) var(--ease-out-soft);}
.rail-btn:active,.icon-btn:active,.tool-btn:active,.send-btn:active,.new-chat-btn:active,
.copy-btn:active,.code-copy:active,.set-nav-btn:active,.session-del:active,.session-exp:active,
.attach-item .remove:active,.toast-close:active,.toast-more:active,#continueNewBtn:active,
.seg-btn:active,.audit-chip:active,.pause-btn:active{transform:scale(.94);}
.pill-btn:active,.ghost-btn:active,.ws-btn:active,.modal-btn:active{transform:scale(.97);}
.send-btn:disabled:active{transform:none;}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px;}
```
同时：删除/收敛旧的三档速率 transition 行（尤其 `transition:all` 必须清零；rail-btn hover 的 --glow 与 .rail-btn.on 的 --glow-strong 删除——发光白名单制：仅焦点/主 CTA hover/流式条/品牌 logo）。

### 2.15 图表（.chart-dot）
```css
.chart-dot{transform-box:fill-box;transform-origin:center;
  transition:transform var(--dur-micro) var(--ease-out-soft);}
.chart-dot:hover{transform:scale(1.67);}
```
（若现有是 r 属性动画/过渡，替换为 transform 版；其余图表 transition 沿用，仅令牌值随第 1 节更新。）

### 2.16 侧栏折叠 + sys-tip + body
- `.sidebar` 折叠：transition 换 `margin-left var(--dur-panel) var(--ease-out-soft)`（替硬编码 .24s var(--ease)；margin-left 是唯一登记的布局属性例外）。
- `.sys-tip`：退场改 class 驱动（JS 配合，见 3.9）：`.sys-tip{animation:v4TipIn var(--dur-comp) var(--ease-out-soft);}`（enter 200ms translateY(-6px)）+ `.sys-tip.out{animation:none;opacity:0;transform:translateY(calc(-1*var(--shift-comp)));transition:opacity var(--dur-comp-out) var(--ease-in-soft),transform var(--dur-comp-out) var(--ease-in-soft);}`（删除 80-utils.js 里的内联 opacity .3s）。
- `body`：`transition:background var(--dur-theme) var(--ease-out-soft),color var(--dur-theme) var(--ease-out-soft);`（替 --dur-base）。
- 主题切换表面白名单（.theming）：
```css
body.theming .rail,body.theming .sidebar,body.theming .header,body.theming .main,
body.theming .panel-head,body.theming .g-card,body.theming .stat-card,body.theming .chart-card,
body.theming .cs-trigger,body.theming .cs-menu,body.theming .input-row,body.theming .toast,
body.theming .modal-card,body.theming .ctx-menu,body.theming .tool-call-item,
body.theming .session-item,body.theming .message .content,body.theming .attach-item,
body.theming .ws-card,body.theming .mcp-row,body.theming .search-hit,body.theming .eff-row,
body.theming .set-nav,body.theming .header-badge,body.theming .pill-btn,body.theming .seg,
body.theming .code-copy,body.theming .token-stat{
  transition-property:background-color,color,border-color,box-shadow,fill,stroke;
  transition-duration:var(--dur-theme);
  transition-timing-function:var(--ease-out-soft);}
```

### 2.17 降级矩阵（替换现有 fx-off 块约 L602-605 与 reduced-motion 块约 L608-612）
```css
/* fx-off 变量级降级：引用令牌的 transition 自动瞬时 */
body.fx-off{
  --dur-press:1ms; --dur-micro:1ms; --dur-micro-out:1ms;
  --dur-comp:1ms; --dur-comp-out:1ms;
  --dur-panel:1ms; --dur-panel-out:1ms; --dur-narr:1ms; --dur-theme:1ms;
  --dur-count:1ms; --dur-chart:1ms;
  --stagger-xs:0ms; --stagger-sm:0ms;
}
/* 无限循环动画必须显式停（变量覆盖对 infinite 无效） */
body.fx-off #auroraBg .au,
body.fx-off .tool-call-item,
body.fx-off .tool-call-item::after{animation:none;}
body.fx-off .stream-bar{box-shadow:none;}   /* 流式条循环保留（功能条），仅去微光 */
body.fx-off .panel,body.fx-off .message,body.fx-off .settings-panel.show{animation:none;}
/* prefers-reduced-motion（现有块保留并集） */
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
  #auroraBg .au{animation:none!important;}
  .tool-call-item::after{display:none!important;}
  .stream-bar{box-shadow:none!important;}
}
/* v4 新增：透明度减弱（无障碍） */
@media (prefers-reduced-transparency: reduce){
  :root{--glass-bg:#f4f6fb; --glass-bg-2:#ffffff; --glass-blur:0px;}
  body.dark{--glass-bg:#171a21; --glass-bg-2:#1a1c22; --glass-blur:0px;}
  .header{background:var(--card-bg);}
  .main{background:var(--main-bg);}
  .modal-mask{background:rgba(16,18,28,.72);backdrop-filter:none;-webkit-backdrop-filter:none;}
}
```

## 3. JS 模块逐文件改造

### 3.1 frontend/src/16-panel-fx.js —— switchPanel 交叉淡化
保留 PANELS/currentPanel/applyFx/toggleFx/initFx 与 R8 提示、analytics 刷新。switchPanel 重写为（方向映射 fwd/back、_panelLeaving 收尸、closeAllCS、降级同步切换）：
```js
const PANEL_ORDER=['chat','sessions','analytics','workspace'];
let _panelLeaving=null;
function switchPanel(name){
  if(!PANELS.includes(name))return;
  const prev=currentPanel; if(prev===name)return;
  currentPanel=name;
  document.querySelectorAll('.rail-btn[data-panel]').forEach(btn=>{
    btn.classList.toggle('on',btn.dataset.panel===name);
  });
  const dir=PANEL_ORDER.indexOf(name)>PANEL_ORDER.indexOf(prev)?'fwd':'back';
  const oldEl=document.getElementById('panel'+prev[0].toUpperCase()+prev.slice(1));
  const newEl=document.getElementById('panel'+name[0].toUpperCase()+name.slice(1));
  if(typeof closeAllCS==='function')closeAllCS();
  if(typeof MOTION!=='undefined'&&MOTION.instant()){
    if(_panelLeaving){_panelLeaving.el.classList.remove('on','leaving','out-fwd','out-back');_panelLeaving=null;}
    if(oldEl)oldEl.classList.remove('on');
    if(newEl)newEl.classList.add('on');
  }else{
    if(_panelLeaving){_panelLeaving.el.classList.remove('on','leaving','out-fwd','out-back');_panelLeaving=null;}
    if(oldEl)oldEl.classList.add('leaving','out-'+dir);
    if(newEl)newEl.classList.add('on','in-'+dir);
    MOTION.onAnimEnd(newEl,'animationend',MOTION.panel()).then(()=>newEl.classList.remove('in-'+dir));
    if(oldEl){_panelLeaving={el:oldEl};
      MOTION.onAnimEnd(oldEl,'animationend',MOTION.panelOut()).then(()=>{
        oldEl.classList.remove('on','leaving','out-'+dir);
        if(_panelLeaving&&_panelLeaving.el===oldEl)_panelLeaving=null;});}
  }
  if(name==='analytics'&&typeof renderAnalytics==='function')renderAnalytics();
  if(name!=='chat'&&typeof isStreaming!=='undefined'&&isStreaming){
    if(typeof addSysTip==='function')addSysTip('正在生成回复，可随时回到「对话」面板查看进度');
  }
}
```

### 3.2 frontend/src/18-toast.js —— toast/模态退场
- toast()：`const close=()=>{...}` 改为：
```js
const close=()=>{ if(t.__closing)return; t.__closing=true;
  t.classList.add('out');
  if(typeof MOTION!=='undefined'&&!MOTION.instant()){
    MOTION.onAnimEnd(t,'transitionend',MOTION.compOut()).then(()=>{try{t.remove();}catch(e){}});
  }else{ try{t.remove();}catch(e){} } };
```
- 队列溢出：`while(box.children.length>=5){const old=box.firstChild; if(old&&old.close)old.close(); else if(old)box.removeChild(old); else break;}`
- `_closeModal()`：保持 resolve/兜底**同步**（先 _settlePendingModal 再拆 DOM），拆 DOM 改退场：
```js
function _closeModal(){
  const m=document.getElementById('modalRoot');
  _settlePendingModal('modal-closed');          // 兜底逻辑保持同步（S22/W22 测试依赖）
  if(!m)return;
  if(typeof MOTION!=='undefined'&&!MOTION.instant()){
    m.classList.add('closing');
    MOTION.onAnimEnd(m,'animationend',MOTION.compOut()).then(()=>{try{m.remove();}catch(e){}});
  }else{ try{m.remove();}catch(e){} }
}
```
- `_modalRoot()`：若已存在 root 且带 `.closing`（正在退场）→ 先 remove 它再创建新的（保证「每次开弹=新元素」的计数语义）；若 root 健康存在 → **复用并 _settlePendingModal('modal-reuse')**（S22 测试 ③「另一查看器重绘模态 → 兜底取消」语义必须保持）；新建路径不 settle（与原代码一致）：
```js
function _modalRoot(){
  let m=document.getElementById('modalRoot');
  if(m&&m.classList&&m.classList.contains('closing')){ try{m.remove();}catch(e){} m=null; }
  if(m){ _settlePendingModal('modal-reuse'); return m; }
  m=document.createElement('div');
  m.id='modalRoot';
  document.body.appendChild(m);
  return m;
}
```

### 3.3 frontend/src/10-custom-select.js —— 下拉退场
`closeAllCS`（或等效关闭函数）：对每个 open 的 wrap 加 `.hiding`，MOTION.onAnimEnd(menu,'animationend',MOTION.compOut()) 后移除 `.open .hiding`；hiding 中重复调用直接 return（防重入）；Esc/外部点击路径不变。若无 closeAllCS 全局函数则改造现有关闭逻辑为显隐模式，并确保存在全局 `closeAllCS`（16-panel-fx 的 switchPanel 调用它——若原本就有则保留原名）。

### 3.4 frontend/src/105-context-menu.js —— 右键菜单退场
hideMenu 改显隐模式：加 `.hiding` → animationend 后移除 `.show .hiding`（MOTION.onAnimEnd 双兜底 + try/catch）；`contextmenu` 处理器里先 `classList.remove('hiding'); void menu.offsetWidth;` 再 `add('show')`（重入场从头播放）；document click / scroll 的 hideMenu 同步。

### 3.5 frontend/src/15-theme.js —— toggleTheme 表面过渡
```js
function toggleTheme(){
  const t=document.body.classList.contains('dark')?'light':'dark';
  const apply=()=>{applyTheme(t);try{localStorage.setItem('glm_theme',t);}catch(e){}};
  if(document.startViewTransition&&typeof MOTION!=='undefined'&&!MOTION.prefersReduced()){
    try{document.startViewTransition(apply);return;}catch(e){}
  }
  document.body.classList.add('theming');apply();
  setTimeout(()=>document.body.classList.remove('theming'),MOTION.theme()+60);
}
```

### 3.6 frontend/src/90-attachments.js —— renderPreview 三态
记录模块级 `_attachCount`：0→n 整条 show（走 .show，退场走 hiding 显隐模式）；n→n+1 只给新项加 `.enter`（animationend 移除）；n→0 加 `.hiding` → animationend 后移除 `.show`/`.hiding`。用 MOTION.onAnimEnd 双兜底。show/hiding 的增删类与 2.12 CSS 对应。

### 3.7 frontend/src/78-analytics.js —— count-up/stagger/draw 编排
- `countUpText` 的硬编码 dur=640 改为 `MOTION.count()`，缓动改 `MOTION.easeOutSoft`（保持 cubic-bezier 求解一致）；reduced-motion 分支保留（瞬时终值）。
- 条形图 `transition-delay:i*60+'ms'` → `'calc(var(--stagger-sm) * '+i+')'`。
- `renderAnalytics` 的 `.drawn` 触发加 60ms 延迟（setTimeout(...,MOTION.staggerSm())）——与面板 L2 入场错峰。
- 其余逻辑不动。

### 3.8 frontend/src/85-session-mgmt.js —— 会话切换容器级过渡
- `renderChatHistory`：首行（重建 innerHTML 前）给 box 加 `.batch`，末行 `requestAnimationFrame(()=>requestAnimationFrame(()=>box.classList.remove('batch')))`——禁止历史逐条重播。
- `switchSession`（或等效切会话函数）：替换其中的 `renderChatHistory(target)` 直调为：
```js
const box=document.getElementById('chatContainer');
if(typeof MOTION!=='undefined'&&MOTION.instant()){renderChatHistory(target);}
else{
  box.classList.add('swapping');
  MOTION.onAnimEnd(box,'transitionend',MOTION.compOut()).then(()=>{
    renderChatHistory(target); void box.offsetWidth; box.classList.remove('swapping');});
}
```
boot 首次调用走 instant 分支（加静默参数或判断首次），避免开屏空容器闪一下。`regenerate` 若也重建历史，同样包 .batch。

### 3.9 frontend/src/80-utils.js —— sys-tip 退场
addSysTip 的内联 `opacity .3s` 删除：创建时元素带 `.sys-tip`（enter 走 CSS v4TipIn 200ms）；关闭/移除时加 `.out` 类 → transitionend/animationend + setTimeout 双兜底后 remove（MOTION.compOut()）。保留现有栈管理与上限逻辑。

### 3.10 frontend/src/60-agent-loop.js —— 流式条
确认 `.stream-bar` 的 classList add/remove('on') 调用不变（CSS 已换 transform 版）——**无需改 JS**，仅核实无 width 相关残留引用。

## 4. 自检（必须全部执行并通过）
1. `C:/Users/陈/.workbuddy/binaries/node/versions/22.22.2-6/node.exe frontend/build.js` → 成功（模块数 ≥40，语法校验过）。
2. `C:/Users/陈/.workbuddy/binaries/python/envs/default/Scripts/python.exe deliverables/design/check_contract.py` → PASS。
3. `C:/Users/陈/.workbuddy/binaries/python/envs/default/Scripts/python.exe -m pytest tests/test_review_fixes.py tests/test_v13_qa.py -q` → 全绿（S22/W22 模态队列、前端 vm 沙箱）。
4. grep 清单（在 frontend/ 下）：
   - `grep -rn "transition:all" frontend/` → 无输出
   - `grep -n "panelIn\|fadeInUp\|slideDown\|indeterminate\|auroraA\|auroraB\|toolPulse\|tipIn" frontend/index.template.html` → 无残留引用（keyframes 定义可删则删）
   - `grep -n "dur-aurora\|dur-glow\|ease-glow" frontend/index.template.html frontend/src/*.js` → 仅允许出现在变量块的兼容别名定义行
   - `grep -n "transition:width\|transition:.*margin\|transition:height" frontend/index.template.html` → 仅 .sidebar margin-left 一处（登记例外）
   - `grep -n "640\|setTimeout(.*200)\|setTimeout(.*2600)\|i \* 60\|opacity .3s" frontend/src/78-analytics.js frontend/src/18-toast.js frontend/src/80-utils.js` → 无残留（18-toast 的 setTimeout(...,200) 已换 onAnimEnd）
5. 报告：改了哪些文件哪些节、每项自检结果输出、grep 输出、与规格的偏差及理由（如有）。

## 5. 已知风险点（来自设计文档，执行时注意）
- 面板交叉淡化：离场面板保留 `.on`（display:flex 不撤）只加 `.leaving`（absolute 脱流），animationend 后才移除 `.on`；入场面板 `.in-*` 必须 z-index:1。
- 模态 keyframes 必须携带 translate(-50%,-50%)。
- fx-off 对 infinite 动画无效，必须显式 animation:none 列表。
- 主题过渡严禁给 `*` 通加 transition。
- 流式条三不变：z-index:10000、position:fixed;top:0、功能条属性（不随 fx-off 停循环，仅去微光）。
- 不得删除任何 DOM id/onclick/callApi 调用点/CSS 契约类。
