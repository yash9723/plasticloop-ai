"use client";

import { Camera, Gauge, Loader2, LocateFixed, Save, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useOnline } from "@/components/common/offline-indicator";
import { Field } from "@/components/common/field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { localized, useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import type { QueuedEvent } from "@/lib/offline/db";
import { compressImage, editQueued, enqueueCollection, syncNow } from "@/lib/offline/sync";
import type { CollectionPayload, WasteStream } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface FormPoint {
  id: string;
  code: string;
  name: string;
  stream_ids: string[];
  device_id?: string | null;
}

interface LatestReading {
  id: string;
  weight_kg: number | null;
  device_timestamp: string;
  is_synthetic: boolean;
  quality: string;
}

const WEIGHT_RE = /^\d{1,4}(\.\d{1,3})?$/;

export function CollectionForm({
  point,
  streams,
  context,
  editing,
  onSaved,
  onCancel,
}: {
  point: FormPoint;
  streams: WasteStream[];
  context?: { pickup_request_id?: string | null; assignment_id?: string | null };
  editing?: QueuedEvent;
  onSaved: (event: QueuedEvent | string) => void;
  onCancel?: () => void;
}) {
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const online = useOnline();
  const allowed = useMemo(() => streams.filter((s) => point.stream_ids.includes(s.id)), [streams, point.stream_ids]);
  const [streamId, setStreamId] = useState<string>(editing?.payload.waste_stream_id ?? allowed[0]?.id ?? "");
  const [weight, setWeight] = useState<string>(editing ? String(editing.payload.weight_kg) : "");
  const [reading, setReading] = useState<LatestReading | null>(null);
  const [notes, setNotes] = useState(editing?.payload.notes ?? "");
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [gps, setGps] = useState<CollectionPayload["gps"]>(editing?.payload.gps ?? null);
  const [busy, setBusy] = useState(false);
  const [readingBusy, setReadingBusy] = useState(false);

  useEffect(() => () => void (photoUrl && URL.revokeObjectURL(photoUrl)), [photoUrl]);

  const weightValid = WEIGHT_RE.test(weight) && Number(weight) > 0 && Number(weight) <= 2000;

  const readScale = async () => {
    if (!point.device_id) return;
    setReadingBusy(true);
    try {
      const r = await api<LatestReading>("/devices/latest-reading", { query: { device_id: point.device_id } });
      if (r.weight_kg === null || r.weight_kg <= 0) throw new Error(t("collector.form.scaleEmpty"));
      setReading(r);
      setWeight(r.weight_kg.toFixed(3).replace(/\.?0+$/, ""));
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setReadingBusy(false);
    }
  };

  const capture = async (file: File | undefined) => {
    if (!file) return;
    const small = await compressImage(file);
    setPhoto(small);
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    setPhotoUrl(URL.createObjectURL(small));
  };

  const locate = () =>
    navigator.geolocation?.getCurrentPosition(
      (pos) => setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy_m: Math.round(pos.coords.accuracy) }),
      () => toast.warning(t("collector.form.gpsUnavailable")),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );

  const save = async (draft: boolean) => {
    if (!user || !streamId || !weightValid) return;
    setBusy(true);
    const stream = streams.find((s) => s.id === streamId);
    // A scale reading is only attached if the weight was not changed by hand afterwards.
    const fromScale = reading && reading.weight_kg !== null && Math.abs(reading.weight_kg - Number(weight)) < 0.0005;
    const payload: CollectionPayload = {
      collection_point_id: point.id,
      waste_stream_id: streamId,
      weight_kg: Number(weight).toFixed(3),
      measurement_source: fromScale ? (reading.is_synthetic ? "simulated_sensor" : "device_measured") : "manual_entry",
      device_reading_id: fromScale ? reading.id : null,
      collected_at: editing?.payload.collected_at ?? new Date().toISOString(),
      gps: gps ?? null,
      notes: notes.trim() || null,
      pickup_request_id: context?.pickup_request_id ?? null,
      assignment_id: context?.assignment_id ?? null,
    };
    try {
      if (editing) {
        const id = await editQueued(editing.event_id, payload, !draft);
        onSaved(id);
      } else {
        const ev = await enqueueCollection({
          userId: user.id,
          payload,
          photo,
          draft,
          pointLabel: `${point.code} · ${point.name}`,
          streamLabel: stream ? localized(stream.labels, stream.label, locale) : "",
        });
        onSaved(ev);
      }
      if (!draft && online) syncNow(user.id).catch(() => {});
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{point.code}</p>
        <p className="text-lg font-semibold leading-tight">{point.name}</p>
      </div>

      <fieldset>
        <legend className="mb-2 text-sm font-medium">{t("collector.form.stream")}</legend>
        <div className="grid grid-cols-2 gap-2">
          {allowed.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setStreamId(s.id)}
              aria-pressed={streamId === s.id}
              className={cn(
                "flex min-h-14 items-center gap-2 rounded-xl border-2 px-3 py-2 text-left text-sm font-medium transition-colors",
                streamId === s.id ? "border-primary bg-secondary" : "border-border bg-card hover:border-primary/40",
              )}
            >
              <span className="size-3 shrink-0 rounded-full" style={{ background: s.color }} aria-hidden />
              {localized(s.labels, s.label, locale)}
            </button>
          ))}
        </div>
        {allowed.length === 0 && <p className="text-sm text-danger-foreground">{t("collector.form.noStreams")}</p>}
      </fieldset>

      <Field label={t("collector.form.weight")} htmlFor="weight" error={weight && !weightValid ? t("validation.weight") : undefined}>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Input
              id="weight"
              inputMode="decimal"
              autoComplete="off"
              value={weight}
              onChange={(e) => setWeight(e.target.value.replace(",", "."))}
              aria-invalid={!!weight && !weightValid}
              className="tabular h-14 pr-12 text-2xl font-semibold"
              placeholder="0.000"
            />
            <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground">kg</span>
          </div>
          {point.device_id && (
            <Button type="button" variant="outline" size="xl" onClick={readScale} disabled={!online || readingBusy} title={online ? undefined : t("collector.form.scaleOffline")}>
              {readingBusy ? <Loader2 className="animate-spin" /> : <Gauge />}
              <span className="hidden sm:inline">{t("collector.form.readScale")}</span>
            </Button>
          )}
        </div>
      </Field>
      {reading && (
        <div className="-mt-3 flex flex-wrap gap-2 text-xs">
          <Badge tone={reading.is_synthetic ? "simulated" : "success"}>
            {reading.is_synthetic ? t("measurement.simulated_sensor") : t("measurement.device_measured")}
          </Badge>
          {Math.abs((reading.weight_kg ?? 0) - Number(weight)) >= 0.0005 && <Badge tone="warning">{t("collector.form.editedByHand")}</Badge>}
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex min-h-14 cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed px-3 text-sm font-medium hover:border-primary/50">
          <Camera className="size-5" aria-hidden />
          {photo ? t("collector.form.retakePhoto") : t("collector.form.addPhoto")}
          <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => capture(e.target.files?.[0])} />
        </label>
        <Button type="button" variant="outline" size="xl" onClick={locate} className={cn(gps && "border-primary text-primary")}>
          <LocateFixed /> {gps ? t("collector.form.gpsAdded", { accuracy: gps.accuracy_m ?? "?" }) : t("collector.form.addGps")}
        </Button>
      </div>
      {photoUrl && (
        <div className="relative w-fit">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={photoUrl} alt={t("collector.form.photoPreview")} className="h-28 rounded-lg object-cover" />
          <button
            type="button"
            onClick={() => {
              setPhoto(null);
              setPhotoUrl(null);
            }}
            className="absolute -right-2 -top-2 rounded-full bg-slate-900 p-1 text-white"
            aria-label={t("collector.form.removePhoto")}
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      <Field label={t("common.notes")} htmlFor="notes" hint={t("common.optional")}>
        <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} rows={2} />
      </Field>

      <div className="grid gap-2 sm:grid-cols-[2fr_1fr_auto]">
        <Button type="button" size="xl" onClick={() => save(false)} disabled={busy || !weightValid || !streamId}>
          {busy ? <Loader2 className="animate-spin" /> : <Save />}
          {online ? t("collector.form.save") : t("collector.form.saveOffline")}
        </Button>
        <Button type="button" size="xl" variant="outline" onClick={() => save(true)} disabled={busy || !weightValid || !streamId}>
          {t("collector.form.saveDraft")}
        </Button>
        {onCancel && (
          <Button type="button" size="xl" variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        )}
      </div>
    </div>
  );
}
