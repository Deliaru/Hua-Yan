import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { SourceImage as ImageResult } from "../types";

export function SourceImage({ docId, span, page, onClose }: {
  docId: string; span: string; page: number; onClose: () => void;
}) {
  const { me } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [image, setImage] = useState<ImageResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    dialog.current!.showModal();
    let alive = true;
    api.sourceImage(docId, page, me, span).then(
      (data) => { if (alive) setImage(data); },
      (e: Error) => { if (alive) setError(e.message); },
    );
    return () => { alive = false; };
  }, [docId, span, page, me]);
  return <dialog ref={dialog} onCancel={onClose} aria-labelledby="source-image-title"
    className="m-auto max-h-[90vh] w-[min(1100px,94vw)] overflow-auto rounded-xl border border-line bg-white p-4 text-ink shadow-xl backdrop:bg-black/40">
    <div className="flex items-center justify-between gap-3">
      <h3 id="source-image-title" className="font-semibold">依据图像 · 第{page}页</h3>
      <button autoFocus type="button" className="btn btn-quiet" onClick={onClose}>关闭图像</button>
    </div>
    <p className="mt-2 break-all text-[12px] text-ink-2">{docId} · {span}</p>
    {!image && !error && <p className="mt-3">正在读取图像……</p>}
    {error && <p role="alert" className="mt-3 text-danger">{error}</p>}
    {image && <figure className="mt-3">
      <figcaption className="mb-2 text-[13px] text-ink-2">
        L{image.level} · {image.kind === "region" ? "已登记区域" : "原页（此块未登记区域，展示整页）"}
        {image.bbox && ` · 区域像素：${image.bbox.join(", ")}`} · {image.width} × {image.height}
      </figcaption>
      <img src={image.image_url} width={image.width} height={image.height}
        alt={`第${image.page}页${image.kind === "region" ? "已登记区域" : "原页"}，依据块${span}`}
        className="h-auto w-full rounded border border-line" />
      <p className="mt-2 break-all text-[12px] text-ink-2">图像指纹：{image.fingerprint}</p>
    </figure>}
  </dialog>;
}
