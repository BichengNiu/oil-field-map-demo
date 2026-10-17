/* Cesium 1.124.0 ships its worker bundle inside Cesium.js. In srcdoc frames,
 * avoid its cross-origin ESM bootstrap: a failed transfer probe otherwise
 * stays pending forever and leaves received terrain tiles without meshes.
 * Use that same pinned bundle through frame-owned Blob URLs instead.
 */
async function installCesiumFrameWorkers(C) {
  if (typeof window.CESIUM_WORKERS !== 'string') {
    throw new Error('Cesium bundled workers are unavailable');
  }
  const urls = new Map();
  const workerUrl = name => {
    if (!urls.has(name)) urls.set(name, URL.createObjectURL(new Blob([
      window.CESIUM_WORKERS, `\nCesiumWorkers[${JSON.stringify(name)}]();`
    ], {type:'application/javascript'})));
    return urls.get(name);
  };
  const transferable = await new Promise((resolve,reject) => {
    const worker = new Worker(workerUrl('transferTypedArrayTest'));
    const timer = setTimeout(() => finish(new Error('Worker startup timed out')),10000);
    function finish(error,value) {
      clearTimeout(timer); worker.terminate();
      if (error) reject(error); else resolve(value);
    }
    worker.onerror = () => finish(new Error('Worker startup failed'));
    worker.onmessage = event => finish(null,event.data?.array?.[0] === 99);
    const sample = new Int8Array([99]);
    try { worker.postMessage({array:sample},[sample.buffer]); }
    catch (_) { finish(null,false); }
  });
  C.TaskProcessor._canTransferArrayBuffer = transferable;
  for (const method of ['scheduleTask','initWebAssemblyModule']) {
    const original = C.TaskProcessor.prototype[method];
    C.TaskProcessor.prototype[method] = function (...args) {
      // Only SDK task names; preserve explicitly supplied external worker URLs.
      if (/^[A-Za-z0-9_]+$/.test(this._workerPath)) {
        this._workerPath = workerUrl(this._workerPath);
      }
      return original.apply(this,args);
    };
  }
  window.addEventListener('pagehide', () => {
    urls.forEach(url => URL.revokeObjectURL(url));
  },{once:true});
}
