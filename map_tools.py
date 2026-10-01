"""Browser controls for the embedded Leaflet map (no server credentials)."""

SCREENSHOT_SCRIPT = r"""
const screenshotControl = L.control({position: 'topright'});
screenshotControl.onAdd = () => {
  const el = L.DomUtil.create('div', 'map-tools');
  el.setAttribute('data-html2canvas-ignore', 'true');
  el.innerHTML = '<button type="button" id="save-map">保存地图 PNG</button>' +
    '<span id="save-status" role="status" aria-live="polite"></span>';
  L.DomEvent.disableClickPropagation(el);
  L.DomEvent.disableScrollPropagation(el);
  return el;
};
screenshotControl.addTo(map);
document.getElementById('save-map').addEventListener('click', async () => {
  const button = document.getElementById('save-map');
  const status = document.getElementById('save-status');
  button.disabled = true;
  status.textContent = '正在生成…';
  try {
    if (typeof html2canvas !== 'function') throw new Error('截图组件未加载，请刷新页面');
    await document.fonts.ready;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const tileImages = [...document.querySelectorAll('#map .leaflet-tile')];
    await Promise.race([
      Promise.all(tileImages.map(img => img.decode())),
      new Promise((resolve, reject) => setTimeout(() => reject(new Error('底图加载超时')), 15000))
    ]);
    if (!tileImages.length || tileImages.some(img => !img.naturalWidth)) {
      throw new Error('底图未加载完成，请等待后重试');
    }
    const canvas = await html2canvas(document.getElementById('map'), {
      useCORS: true, allowTaint: false, backgroundColor: '#e8eef4',
      scale: Math.min(window.devicePixelRatio || 1, 2), logging: false,
      imageTimeout: 15000
    });
    const blob = await new Promise((resolve, reject) => canvas.toBlob(
      value => value ? resolve(value) : reject(new Error('图片编码失败')), 'image/png'));
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `energy-map_${screenshotDate}_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status.textContent = 'PNG 已生成';
  } catch (error) {
    status.textContent = `保存失败：${error.message || error}。可使用浏览器截图。`;
  } finally {
    button.disabled = false;
  }
});
"""
