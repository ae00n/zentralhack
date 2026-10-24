"use client";

// A batch (UPLOAD_PLAN step 2). "challenge" is SG.CIV.17, processed before the event: the desk as before.
// Every other id is an uploaded batch.
import { useParams } from "next/navigation";
import BatchView from "@/components/batch/BatchView";
import Arbeitsplatz from "@/components/desk/Arbeitsplatz";

export default function StapelPage() {
  const id = decodeURIComponent(String(useParams<{ id: string }>().id));
  return id === "challenge" ? <Arbeitsplatz /> : <BatchView id={id} />;
}
