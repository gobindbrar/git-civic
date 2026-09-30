export default function Journey() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-bg text-text font-body">
      <div className="absolute left-[6vw] top-[8vh] h-[0.7vh] w-[8vw] bg-accent" aria-hidden="true" />
      <h1 className="absolute left-[6vw] top-[14vh] font-display text-[5.4vw] font-medium tracking-[-0.045em]">The resident journey</h1>
      <div className="absolute left-[6vw] right-[6vw] top-[36vh]">
        <p className="border-t border-[#d4d1c4] py-[4.2vh] text-[2.5vw] leading-[1.25]"><span className="font-extrabold text-primary">Discover:</span> filter by city, topic, and jurisdiction</p>
        <p className="border-t border-[#d4d1c4] py-[4.2vh] text-[2.5vw] leading-[1.25]"><span className="font-extrabold text-primary">Understand:</span> read published agenda items and optional cited AI briefs</p>
        <p className="border-t border-[#d4d1c4] py-[4.2vh] text-[2.5vw] leading-[1.25]"><span className="font-extrabold text-primary">Participate:</span> RSVP and add a calendar invite</p>
        <p className="border-y border-[#d4d1c4] py-[4.2vh] text-[2.5vw] leading-[1.25]"><span className="font-extrabold text-primary">Passport:</span> check in and export your activity</p>
      </div>
      <span className="absolute bottom-[4vh] right-[6vw] text-[1.5vw] text-muted">04 / 08</span>
    </div>
  );
}