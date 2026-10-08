"use client";

import { Copy, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useT } from "@/i18n/i18n";
import type { DeviceCreated } from "@/lib/types";

/** Shows a freshly issued device key exactly once, with the connection details the firmware needs. */
export function KeyReveal({ created, onClose }: { created: DeviceCreated | null; onClose: () => void }) {
  const { t } = useT();
  const copy = (text: string) => navigator.clipboard?.writeText(text).then(() => toast.success(t("common.copied")));
  return (
    <Dialog open={!!created} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-5" /> {t("devices.keyTitle")}
          </DialogTitle>
          <DialogDescription>{t("devices.keyOnce")}</DialogDescription>
        </DialogHeader>
        {created && (
          <div className="grid gap-3 text-sm">
            {[
              [t("devices.mqttUser"), created.mqtt_username],
              [t("devices.key"), created.device_key],
              [t("devices.topic"), created.topics.telemetry],
            ].map(([label, value]) => (
              <div key={label}>
                <p className="mb-1 text-xs font-medium text-muted-foreground">{label}</p>
                <div className="flex items-center gap-2">
                  <code className="min-w-0 flex-1 break-all rounded-md bg-muted px-2 py-1.5 font-mono text-xs">{value}</code>
                  <Button size="icon" variant="ghost" aria-label={`${t("common.copy")} ${label}`} onClick={() => copy(value)}>
                    <Copy />
                  </Button>
                </div>
              </div>
            ))}
            <Alert tone="warning">{t("devices.keyWarning")}</Alert>
          </div>
        )}
        <DialogFooter>
          <Button onClick={onClose}>{t("devices.keyStored")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
