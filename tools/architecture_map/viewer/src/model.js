// The architecture model, written into the page by the build (vite.config.mjs).
export function readModel() {
  const element = document.getElementById('model');
  if (!element) throw new Error('This page holds no model: rebuild the viewer.');
  const model = JSON.parse(element.textContent);
  if (model.schema !== 1) {
    throw new Error(`This viewer reads model schema 1, not ${model.schema}: rebuild the viewer.`);
  }
  return model;
}
