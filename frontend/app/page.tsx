// Start (UPLOAD_PLAN step 2): step 1 of the flow. Upload a ZIP, a folder or images, then the batches.
// The SG.CIV.17 desk that used to be here lives at /stapel/challenge.
import BatchCards from "@/components/upload/BatchCards";
import UploadDrop from "@/components/upload/UploadDrop";

export default function StartPage() {
  return (
    <main className="mx-auto w-full max-w-[960px] px-4 py-8 sm:py-12">
      <h1 className="text-h1 text-ink-strong">Fotos erschliessen</h1>
      <p className="mt-2 max-w-[640px] text-base text-ink-muted">
        Fotos hochladen, der Agent bestimmt Ortschaft, Gemeinde, Gebäude, See/Fluss/Berg und Strasse mit Quellen und
        Konfidenz. Unsichere Fotos prüfen Sie danach, das Ergebnis gibt es als Excel.
      </p>
      <UploadDrop className="mt-6" />

      <section className="mt-10" aria-labelledby="stapel">
        <h2 id="stapel" className="text-h2 text-ink-strong">
          Stapel
        </h2>
        <div className="mt-3">
          <BatchCards />
        </div>
      </section>
    </main>
  );
}
