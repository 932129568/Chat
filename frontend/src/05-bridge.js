/* ================= 桥接 ================= */
async function callApi(name, argsArray, timeoutMs) {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api[name]) {
    throw new Error('pywebview bridge 未就绪: ' + name);
  }
  const args = argsArray || [];
  // 修复 ㉞：timeoutMs 显式判断（原 `timeoutMs || 60000` 吞 0 值）
  const ms = (typeof timeoutMs === 'number' && timeoutMs > 0) ? timeoutMs : 60000;
  let timer = null;
  try {
    // 修复 ㉞：竞速定时器 clearTimeout——成功返回后不再空留一个 60s 后才触发的 reject
    return await Promise.race([
      window.pywebview.api[name](...args),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('调用超时: ' + name)), ms); })
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
/* 修复 ㉞：backendErrorMsg 为死代码（全项目无调用点）——已删除 */
