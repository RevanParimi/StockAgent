import { useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Vector3 } from 'three';

/**
 * Moves the HTML labels to their places in the 3D world. Labels that would overlap are
 * pushed up, the less important ones first. A label's size is measured once.
 */
export default function Projector({ anchors, labels, rootRef }) {
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const point = useMemo(() => new Vector3(), []);
  const measured = useMemo(() => new WeakMap(), []);

  useFrame(() => {
    camera.updateMatrixWorld();
    const wanted = [];
    for (const anchor of anchors) {
      const element = labels.current.get(anchor.key);
      if (!element) continue;
      point.set(...anchor.pos).project(camera);
      if (anchor.hidden || point.z > 1 || Math.abs(point.x) > 1.15 || Math.abs(point.y) > 1.15) {
        element.style.visibility = 'hidden';
        continue;
      }
      let box = measured.get(element);
      if (!box || !box.width) {
        box = { width: element.offsetWidth, height: element.offsetHeight };
        measured.set(element, box);
      }
      wanted.push({
        element, box, priority: anchor.priority,
        x: ((point.x + 1) / 2) * size.width,
        y: ((1 - point.y) / 2) * size.height,
      });
    }
    wanted.sort((a, b) => a.priority - b.priority || b.y - a.y);
    const placed = [];
    for (const item of wanted) {
      const half = item.box.width / 2;
      let bottom = item.y;
      for (let tries = 0; tries < 12; tries += 1) {
        const hit = placed.find((p) => Math.abs(p.x - item.x) < p.half + half
          && bottom > p.bottom - p.height && bottom - item.box.height < p.bottom);
        if (!hit) break;
        bottom = hit.bottom - hit.height - 2;
      }
      placed.push({ x: item.x, half, bottom, height: item.box.height });
      item.element.style.transform =
        `translate(${Math.round(item.x - half)}px, ${Math.round(bottom - item.box.height)}px)`;
      item.element.style.visibility = 'visible';
    }
    const root = rootRef.current;
    if (root && root.dataset.ready !== 'true') root.dataset.ready = 'true';
  });
  return null;
}
