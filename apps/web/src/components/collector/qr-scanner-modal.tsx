"use client";

import { Camera, Keyboard } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n/i18n";

/** Camera QR scanning (qr-scanner uses the native BarcodeDetector when available, a web worker otherwise). */
export function QrScannerModal({
  open,
  onOpenChange,
  onResult,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onResult: (value: string) => void;
}) {
  const { t } = useT();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState("");

  const handleOpenChange = (next: boolean) => {
    if (!next) setError(null);
    onOpenChange(next);
  };

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    let scanner: { stop: () => void; destroy: () => void } | null = null;
    (async () => {
      if (!window.isSecureContext) {
        setError(t("collector.cameraInsecure"));
        return;
      }
      try {
        const { default: QrScanner } = await import("qr-scanner");
        if (cancelled || !videoRef.current) return;
        const instance = new QrScanner(
          videoRef.current,
          (result) => {
            instance.stop();
            onResult(result.data);
            onOpenChange(false);
          },
          { preferredCamera: "environment", highlightScanRegion: true, returnDetailedScanResult: true, maxScansPerSecond: 8 },
        );
        scanner = instance;
        await instance.start();
      } catch {
        if (!cancelled) setError(t("collector.cameraError"));
      }
    })();
    return () => {
      cancelled = true;
      scanner?.stop();
      scanner?.destroy();
    };
  }, [open, onOpenChange, onResult, t]);

  const submitManual = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manual.trim()) return;
    onResult(manual.trim());
    setManual("");
    handleOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Camera className="size-5" aria-hidden /> {t("collector.scanTitle")}
          </DialogTitle>
          <DialogDescription>{t("collector.scanHint")}</DialogDescription>
        </DialogHeader>
        <div className="relative overflow-hidden rounded-xl bg-slate-950">
          <video ref={videoRef} className="aspect-square w-full object-cover" muted playsInline />
        </div>
        {error && (
          <Alert tone="warning">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <form onSubmit={submitManual} className="flex gap-2">
          <label htmlFor="manual-code" className="sr-only">
            {t("collector.codePlaceholder")}
          </label>
          <Input
            id="manual-code"
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder={t("collector.codePlaceholder")}
            autoCapitalize="characters"
            className="h-12 text-base"
          />
          <Button type="submit" size="lg" variant="outline">
            <Keyboard /> {t("collector.find")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
