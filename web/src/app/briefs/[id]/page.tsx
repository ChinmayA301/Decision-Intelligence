import { notFound } from "next/navigation";
import { DecisionBrief } from "@/types/api";
import BriefViewer from "@/components/BriefViewer";

async function getBrief(id: string): Promise<DecisionBrief | null> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const res = await fetch(`${apiUrl}/briefs/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch brief: ${res.status}`);
  return res.json();
}

export default async function BriefPage({ params }: { params: { id: string } }) {
  const brief = await getBrief(params.id);
  if (!brief) notFound();

  return (
    <div>
      <div className="mb-6 text-xs text-gray-400">
        Shared brief · Generated {new Date(brief.created_at).toLocaleDateString()}
      </div>
      {/* Static view of a shared brief — the "New decision" button links home */}
      <BriefViewer brief={brief} />
      <div className="mt-8 pt-6 border-t border-gray-200 text-center">
        <a
          href="/"
          className="text-sm text-blue-600 hover:underline"
        >
          Analyze your own decision →
        </a>
      </div>
    </div>
  );
}
