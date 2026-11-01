import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { SourceImage as ImageResult } from "../types";

export function SourceImage({ docId, span, page, onClose, initialImage }: {
  docId: string; span?: string; page: number; onClose: () => void; initialImage?: ImageResult;
}) {
  const { me } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [image, setImage] = useState<ImageResult | null>(initialImage ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  useEffect(() => {
    let alive = true;
    setImage(initialImage ?? null); setError(null);
    if (!initialImage) api.sourceImage(docId, page, me, span).then(
      (data) => { if (alive) setImage(data); },
      (e: Error) => { if (alive) setError(e.message); },
    );
    return () => { alive = false; };
  }, [docId, span, page, me, initialImage]);
  return <dialog ref={dialog} onCancel={onClose} aria-labelledby="source-image-title"
    className="m-auto max-h-[94vh] w-[min(1400px,96vw)] overflow-auto rounded-xl border border-line bg-white p-4 text-ink shadow-xl backdrop:bg-black/40">
    <div className="flex items-center justify-between gap-3">
      <h3 id="source-image-title" className="font-semibold">依据图像 · 第{page}页</h3>
      <button autoFocus type="button" className="btn btn-quiet" onClick={onClose}>关闭图像</button>
    </div>
    {!image && !error && <p className="mt-3">正在读取图像……</p>}
    {error && <p role="alert" className="mt-3 text-danger">{error}</p>}
    {image && <figure className="mt-3">
      <figcaption className="mb-2 text-[13px] text-ink-2">
        L{image.level} · {image.kind === "region" ? "已登记区域" : "原页（此块未登记区域，展示整页）"}
      </figcaption>
      <img src={image.image_url} width={image.width} height={image.height}
        alt={`第${image.page}页${image.kind === "region" ? "已登记区域" : "原页"}，依据块${span ?? "整页"}`}
        className="h-auto w-full rounded border border-line" />
      <ImageDetails image={image} />
    </figure>}
  </dialog>;
}

function ImageDetails({ image }: { image: ImageResult }) {
  return <details className="mt-3 text-[12px] text-ink-2">
    <summary className="cursor-pointer">查看图像定位与指纹</summary>
    <p className="mt-2 break-all">{image.doc_id} · {image.span ?? "整页"} · 第{image.page}页 · L{image.level}</p>
    <p>{image.width} × {image.height}{image.bbox && ` · 区域像素：${image.bbox.join(", ")}`}</p>
    <p className="break-all">图像指纹：{image.fingerprint}</p>
  </details>;
}

// 放大复用本次服务端返回的图像，不重复请求；切图和切身份均重新经原API读取。
export function SourceImageCard({ docId, span, page, label }: {
  docId: string; span?: string; page: number; label: string;
}) {
  const { me } = useApp();
  const [image, setImage] = useState<ImageResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enlarged, setEnlarged] = useState(false);
  useEffect(() => {
    let alive = true;
    setImage(null); setError(null); setEnlarged(false);
    api.sourceImage(docId, page, me, span).then(
      (data) => { if (alive) setImage(data); },
      (e: Error) => { if (alive) setError(e.message); },
    );
    return () => { alive = false; };
  }, [docId, span, page, me]);
  return <figure className="rounded-xl border border-line bg-white p-3">
    <figcaption className="mb-3 flex flex-wrap justify-between gap-2"><strong>{label}</strong><span className="text-[12px] text-ink-2">Office原生依据</span></figcaption>
    {!image && !error && <p role="status" className="py-12 text-center text-ink-2">正在读取原生图像……</p>}
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-danger">{error}</p>}
    {image && <>
      <button type="button" className="block w-full cursor-zoom-in" onClick={() => setEnlarged(true)} aria-label={`放大${label}`}>
        <img src={image.image_url} width={image.width} height={image.height} alt={`${label}，第${image.page}页${image.kind === "region" ? "高清区域裁图" : "原页图像"}`}
          className="h-auto max-h-[640px] w-full rounded border border-line object-contain" />
      </button>
      <p className="mt-2 text-[12px] text-ink-2">{image.kind === "region" ? "已登记区域高清裁图" : "原页图像（未提供区域或此块未登记区域）"} · 点击图片放大</p>
      <ImageDetails image={image} />
      {enlarged && <SourceImage docId={docId} span={span} page={page} initialImage={image} onClose={() => setEnlarged(false)} />}
    </>}
  </figure>;
}
