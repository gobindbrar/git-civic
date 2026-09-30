const base = import.meta.env.BASE_URL;

export default function Meeting() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] font-display text-[5.1vw] font-medium tracking-[-0.045em]">A real meeting, clearly sourced</h1>
      <div className="absolute left-[6vw] right-[6vw] top-[34vh] space-y-[3vh]">
        <p className="text-[2.15vw] font-semibold leading-[1.25]">SF Budget and Finance Committee · Sep 30, 2026 · 10:00 AM PDT</p>
        <p className="text-[2.15vw] font-semibold leading-[1.25]">Published agenda: Final; official meeting and agenda links</p>
        <p className="text-[2.15vw] font-semibold leading-[1.25]">Source path: official Legistar website fallback, not the Events API</p>
      </div>
      <div className="absolute left-[6vw] top-[75vh] w-[35vw] border-t border-[#d4d1c4] pt-[2vh]">
        <a href="https://sfgov.legistar.com/MeetingDetail.aspx?ID=1446421&amp;GUID=A214F14A-9FCD-4F0D-8428-24ADB4B08367&amp;Options=info%7C&amp;Search=" target="_blank" rel="noopener noreferrer" className="text-[1.7vw] leading-[1.35] text-primary underline underline-offset-[0.4vw]">Source: SF Legistar meeting ID 1446421 · checked Sep 29, 2026</a>
      </div>
      <div className="absolute left-[46vw] top-[61vh] h-[32vh] w-[48vw] overflow-hidden border-[0.4vw] border-[#fbfaf5] shadow-[0_1vw_3vw_rgba(23,60,58,0.13)]">
        <img src={`${base}git-civic-meeting.jpg`} crossOrigin="anonymous" alt="Real GIT Civic meeting page with official Legistar site source label" className="h-full w-full object-cover object-[35%_20%]" />
      </div>
      <span className="absolute bottom-[4vh] left-[6vw] text-[1.5vw] text-muted">05 / 08</span>
    </div>
  );
}