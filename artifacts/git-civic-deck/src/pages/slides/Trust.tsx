export default function Trust() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] font-display text-[5.4vw] font-medium tracking-[-0.045em]">Proof with clear limits</h1>
      <div className="absolute left-[6vw] right-[6vw] top-[36vh]">
        <p className="border-t border-[#d4d1c4] py-[3.6vh] text-[2.22vw] leading-[1.2]">Official-source badge: provenance, not independent fact-checking</p>
        <p className="border-t border-[#d4d1c4] py-[3.6vh] text-[2.22vw] leading-[1.2]">Sample listings: fictional; community posts: unverified</p>
        <p className="border-t border-[#d4d1c4] py-[3.6vh] text-[2.22vw] leading-[1.2]">Self-report and organizer code: limited evidence</p>
        <p className="border-t border-[#d4d1c4] py-[3.6vh] text-[2.22vw] leading-[1.2]">Presence and document methods: simulated only</p>
        <p className="border-y border-[#d4d1c4] py-[3.6vh] text-[2.22vw] leading-[1.2]">Passport is browser-linked; no government certification</p>
      </div>
      <span className="absolute bottom-[4vh] right-[6vw] text-[1.5vw] text-muted">06 / 08</span>
    </div>
  );
}