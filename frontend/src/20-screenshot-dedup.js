/* ================= dHash 截图去重 ================= */
function dHashOfDataUrl(dataUrl) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      const w = 9, h = 8, c = document.createElement('canvas');
      c.width = w; c.height = h;
      const ctx = c.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(img, 0, 0, w, h);
      const d = ctx.getImageData(0, 0, w, h).data, g = [];
      for (let i = 0; i < w * h; i++)
        g.push(0.299 * d[i*4] + 0.587 * d[i*4+1] + 0.114 * d[i*4+2]);
      const bits = [];
      for (let y = 0; y < h; y++)
        for (let x = 0; x < w - 1; x++)
          bits.push(g[y*w + x] > g[y*w + x + 1] ? 1 : 0);
      resolve(bits);
    };
    img.onerror = () => resolve(null);
    img.src = dataUrl;
  });
}
function hammingDist(a, b) {
  let n = 0;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) n++;
  return n;
}
async function shotDedup(comp) {
  const h = await dHashOfDataUrl(comp);
  if (!h) return null;
  if (lastShotHash && hammingDist(h, lastShotHash) <= 5) {
    return '屏幕与上次截图基本一致，沿用上次分析即可。';
  }
  lastShotHash = h;
  return null;
}
