(() => {
  "use strict";

  const app = document.getElementById("app");
  const nav = document.querySelector(".topnav");
  const menuToggle = document.getElementById("menu-toggle");
  const toastRegion = document.getElementById("toast-region");

  const state = { events: [], query: "", category: "", jurisdiction: "", requestId: 0 };
  const categories = ["Public meeting", "Planning & Development", "Education", "Public Safety", "Transportation", "Other"];
  const esc = (value = "") => String(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const formatDate = (value, options = { month: "short", day: "numeric", year: "numeric" }, zone = "") => {
    if (!value) return "Date to be confirmed";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? esc(value) : new Intl.DateTimeFormat(undefined, { ...options, ...(zone ? { timeZone: zone } : {}) }).format(date);
  };
  const formatTime = (value, zone = "") => {
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", ...(zone ? { timeZone: zone, timeZoneName: "short" } : {}) }).format(date);
  };
  const categoryOptions = (selected = "") => categories.map((c) => `<option value="${esc(c)}" ${c === selected ? "selected" : ""}>${esc(c)}</option>`).join("");
  const demoTag = (event) => event.is_demo ? '<span class="demo-tag">DEMO LISTING · NOT LIVE</span>' : event.source_status === "verified_feed" ? '<span class="official-tag">OFFICIAL LEGISTAR FEED · SOURCE CHECKED</span>' : event.source_status === "verified_site" ? '<span class="official-tag">OFFICIAL LEGISTAR SITE · SOURCE CHECKED</span>' : event.source_status === "stale_feed" ? '<span class="demo-tag">OFFICIAL SOURCE · CHECK EXPIRED</span>' : '<span class="demo-tag">COMMUNITY LISTING · NOT SOURCE-CHECKED</span>';
  const isOfficialLegistar = (event) => !event.is_demo
    && Boolean(event.source_record_id)
    && ["verified_feed", "verified_site", "stale_feed"].includes(event.source_status);
  const verificationLabel = (method) => ({
    organizer_code: "Organizer Code Confirmed",
    self_reported: "Self Reported"
  })[method] || "Unverified activity";
  const verificationNote = (method) => method === "self_reported"
    ? "Self-reported; not externally verified."
    : method === "organizer_code"
      ? "Organizer code confirmed; not government-certified."
      : "Verification method unavailable.";
  const stages = [
    ["DISCOVER", "Find meetings and civic opportunities near you."],
    ["UNDERSTAND", "Read a neutral preview or request a cited AI brief for a checked official listing when available."],
    ["PARTICIPATE", "Get meeting details, source links when available, and participation information."],
    ["VERIFY", "Record attendance as Self Reported or Organizer Code Confirmed."]
  ];
  function stageStrip() {
    return `<section class="how-strip" id="how"><div class="how-heading"><div class="eyebrow">How it works</div><h3>Participation, step by step.</h3></div>${stages.map(([heading, text], i) => `<div class="how-step"><span class="step-num">0${i+1}</span><h4>${heading}</h4><p>${text}</p></div>`).join("")}</section>`;
  }
  function intelligencePanel() {
    const agents = [
      ["GIT Coordinator", "Sends checked official agenda evidence into a Band room when configured."],
      ["GIT Source Verifier", "Checks source integrity before handing verified rows to the Analyst."],
      ["GIT Agenda Analyst", "Drafts a cited, neutral brief from the verified rows."],
      ["GIT Civic Critic", "Can block unsupported claims and require a revised draft."]
    ];
    return `<section class="intelligence-panel"><div><span class="demo-tag">WORKFLOW OVERVIEW · NOT A LIVE RUN</span><h2>GIT Intelligence</h2><p>For a checked official meeting, request a cited AI brief to see the actual result and workflow status. If Band cannot complete, a separately labeled single-agent brief is used.</p></div><div class="agent-feed">${agents.map(([name, message], i) => `<div class="agent-item"><span>0${i+1}</span><div><strong>${name}</strong><p>${message}</p></div></div>`).join("")}</div></section>`;
  }

  function briefStatus(brief, event) {
    const band = brief.mode === "band";
    const rows = [
      ["Government Data", event.source_status === "verified_site" ? "LIVE · OFFICIAL SITE FALLBACK" : "LIVE · OFFICIAL FEED"],
      ["AI Brief", band ? "BAND MULTI-AGENT" : brief.mode === "cached" ? "CACHED AI BRIEF" : "SINGLE-AGENT FALLBACK"],
      ["Source Verification", band ? brief.source_verification : "NOT RUN"],
      ["Civic Critic", band ? brief.civic_critic : "NOT RUN"]
    ];
    return `<div class="brief-status"><strong>Developer / demo status</strong>${rows.map(([key, value]) => `<div><span>${esc(key)}</span><b>${esc(value)}</b></div>`).join("")}</div>${band ? `<div class="brief-workflow"><strong>Band workflow · room ${esc(brief.band_room_id)}</strong>${(brief.workflow || []).map((step) => `<div>✓ ${esc(step)}</div>`).join("")}${brief.revision_requested ? "<p>Evidence review requested a revision.</p>" : ""}</div>` : ""}`;
  }

  async function request(url, options = {}) {
    if (window.gitCivicAuthReady) {
      await Promise.race([window.gitCivicAuthReady, new Promise((resolve) => setTimeout(resolve, 2500))]);
    }
    const response = await fetch(url, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(window.gitCivicAuth?.getToken ? { Authorization: `Bearer ${await window.gitCivicAuth.getToken()}` } : {}),
        ...(options.headers || {})
      }
    });
    let data;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) {
      const error = new Error(data.error || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function toast(message, isError = false) {
    const item = document.createElement("div");
    item.className = `toast${isError ? " is-error" : ""}`;
    item.textContent = message;
    toastRegion.append(item);
    window.setTimeout(() => item.remove(), 3600);
  }

  function go(path) {
    history.pushState({}, "", path);
    document.getElementById("modal-root").innerHTML = "";
    nav.classList.remove("is-open");
    menuToggle.setAttribute("aria-expanded", "false");
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function route() {
    const path = location.pathname.replace(/\/+$/, "") || "/";
    if (path === "/") return { name: "home" };
    if (path === "/new") return { name: "new" };
    if (path === "/my-activity" || path === "/passport") return { name: "activity" };
    if (path === "/how-it-works") return { name: "how" };
    if (path === "/about") return { name: "about" };
    const detail = path.match(/^\/events\/([^/]+)$/);
    if (detail) return { name: "detail", id: decodeURIComponent(detail[1]) };
    const shared = path.match(/^\/passport\/share\/([^/]+)$/);
    if (shared) return { name: "shared-passport", slug: decodeURIComponent(shared[1]) };
    return { name: "not-found" };
  }

  function updateNav(page) {
    document.querySelectorAll("[data-nav]").forEach((link) => link.classList.toggle("active", link.dataset.nav === page));
  }

  function skeleton() {
    return `<div class="loading-row" aria-hidden="true"></div><div class="loading-row" aria-hidden="true"></div><div class="loading-row" aria-hidden="true"></div>`;
  }

  function eventRow(event, checkedIn = false) {
    const date = event.starts_at ? new Date(event.starts_at) : null;
    const dateIsValid = date && !Number.isNaN(date.getTime());
    const shortDate = dateIsValid ? formatDate(event.starts_at, { month: "short", day: "numeric" }, event.time_zone).split(" ") : ["—", "—"];
    const url = `/events/${encodeURIComponent(event.id)}`;
    return `<a class="event-row" href="${url}" data-link>
      <span class="date-block"><span class="month">${esc(shortDate[0] || "")}</span><span class="day">${esc(shortDate[1] || "—")}</span></span>
       <span class="event-details">${demoTag(event)}${event.is_cancelled ? '<span class="demo-tag">EVENT CANCELLED</span>' : ""}<span class="event-title">${esc(event.title)}</span><span class="event-meta"><span>${esc(formatTime(event.starts_at, event.time_zone) || "Time to be confirmed")}</span><span>${esc(event.location || event.city || "Location to be confirmed")}</span></span><span class="event-organizer">${esc(event.organizer || "Community organizer")} · ${esc(event.jurisdiction || "City")}</span><span class="topic-line">${(event.topics || []).map((t) => `<span>${esc(t)}</span>`).join("")}</span></span>
      <span class="event-badge"><span class="event-category">${esc(event.category || "Community")}</span><span class="view-meeting">View Meeting ↗</span>${checkedIn ? '<span class="receipt-tag" style="display:block;margin-top:9px">RECORDED</span>' : ""}</span>
      <span class="row-arrow" aria-hidden="true">↗</span>
    </a>`;
  }

  function emptyState() {
    return `<section class="empty-state">
      <div class="empty-content">
        <div class="eyebrow">A good place to begin</div>
        <h3>No meetings on the board just yet.</h3>
        <p>There aren’t any local events listed here right now. Add a public meeting you know about, or check back soon. When something’s posted, this is where you’ll find the details and a way to say you’re going.</p>
        <div class="empty-actions"><a class="button-primary" href="/new" data-link>Post a public event <span>↗</span></a><button type="button" class="button-secondary" id="refresh-events">Check again <span>↻</span></button></div>
      </div>
      <div class="empty-art" aria-hidden="true"><span class="art-sun"></span><span class="art-horizon"></span><span class="art-steps"></span><span class="art-figure"></span><span class="art-caption">A SEAT IS WAITING</span></div>
    </section>`;
  }

  function homeView() {
    return `<div class="page">
      <section class="home-hero">
        <div class="hero-copy">
           <div class="eyebrow">GIT Civic · Get Involved Today</div>
           <h1>Find it. Show up.<br><em>Prove it.</em></h1>
           <p class="hero-description">Discover what is happening in your government, understand why it matters, and build a verified record of your civic participation.</p>
           <div class="hero-actions"><a class="button-primary" href="#discover">Find Civic Events ↗</a><a class="button-secondary" href="/passport" data-link>View My Civic Passport ↗</a></div>
        </div>
        <aside class="hero-aside"><div class="aside-number">01 / YOUR NEXT STEP</div><p>Local government isn’t somewhere else. It’s the places, plans, and people right around you.</p></aside>
      </section>
       <form class="search-wrap" id="search-form" role="search">
         <label class="search-field"><span class="sr-only">City or ZIP code</span><svg viewBox="0 0 24 24" fill="none" stroke-width="1.7" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8"></circle><path d="m16 16 5 5"></path></svg><input id="search-query" type="search" placeholder="Enter city or ZIP code" value="${esc(state.query)}"></label>
        <label class="search-field select-wrap"><span class="sr-only">Filter by category</span><select id="search-category"><option value="">All categories</option>${categoryOptions(state.category)}</select></label>
        <button class="search-button" type="submit">Find a meeting <span aria-hidden="true">↗</span></button>
      </form>
       <div class="filter-row"><label>Jurisdiction <select id="search-jurisdiction"><option value="">All jurisdictions</option>${["City","County","State","Federal"].map((j) => `<option value="${j}" ${state.jurisdiction === j ? "selected" : ""}>${j}</option>`).join("")}</select></label><span>Search also matches titles, addresses, and organizers. Sample listings are not live notices.</span></div>
        <div class="section-head" id="discover"><h2>On the civic calendar</h2><p id="result-count"></p></div>
        <p class="feed-status" id="source-status" role="status">Checking the official San Francisco meeting source…</p>
      <div class="results-grid" id="event-results">${skeleton()}</div>
       ${stageStrip()}
       ${intelligencePanel()}
    </div>`;
  }

  async function loadEvents() {
    const holder = document.getElementById("event-results");
    if (!holder) return;
    const thisRequest = ++state.requestId;
    holder.innerHTML = skeleton();
    try {
      const data = await request("/api/events");
      if (thisRequest !== state.requestId || !document.getElementById("event-results")) return;
      state.events = Array.isArray(data.events) ? data.events : [];
       const status = data.live_status || {};
       const statusBox = document.getElementById("source-status");
       if (statusBox) statusBox.textContent = status.state === "live"
         ? `San Francisco: official Legistar ${status.mode === "official_site" ? "website fallback (Events API unavailable)" : "Events API"} checked. Seattle: ${data.feed_error ? "feed unavailable" : "public feed connected"}. Demo listings remain marked.`
         : `San Francisco: official source ${status.state === "disabled" ? "disabled" : "temporarily unavailable"}. Seattle: ${data.feed_error ? "feed unavailable" : "public feed connected"}. Demo listings are not live notices.`;
       if (data.feed_error) toast("Official feed could not refresh. Check the organizer’s site for current details.", true);
      const query = state.query.trim().toLowerCase();
      const filtered = state.events.filter((event) => {
        const haystack = [event.title, event.location, event.city, event.organizer, event.description, ...(event.topics || [])].join(" ").toLowerCase();
        return (!query || haystack.includes(query)) && (!state.category || event.category === state.category) && (!state.jurisdiction || event.jurisdiction === state.jurisdiction);
      });
      const counter = document.getElementById("result-count");
      counter.textContent = state.events.length ? `${filtered.length} ${filtered.length === 1 ? "EVENT" : "EVENTS"}${query || state.category || state.jurisdiction ? " FOUND" : " LISTED"}` : "A COMMUNITY-SHARED CALENDAR";
      if (!filtered.length) {
        holder.innerHTML = state.events.length
          ? `<section class="empty-state"><div class="empty-content"><div class="eyebrow">No matches this time</div><h3>Nothing found for those filters.</h3><p>Try another phrase or category. Local listings are added by community members, so you can also post a meeting you know about.</p><div class="empty-actions"><button type="button" class="button-secondary" id="clear-search">Clear filters</button><a class="button-primary" href="/new" data-link>Post an event <span>↗</span></a></div></div><div class="empty-art" aria-hidden="true"><span class="art-sun"></span><span class="art-horizon"></span><span class="art-steps"></span><span class="art-figure"></span><span class="art-caption">A SEAT IS WAITING</span></div></section>`
          : emptyState();
      } else {
        holder.innerHTML = filtered.map((event) => eventRow(event)).join("");
      }
    } catch (error) {
      if (thisRequest !== state.requestId || !document.getElementById("event-results")) return;
      holder.innerHTML = `<div class="error-box"><span>We couldn’t load the neighborhood calendar. ${esc(error.message)}</span><button type="button" id="retry-events">Try again</button></div>`;
    }
  }

  function newView() {
    return `<div class="page subpage">
      <header class="subpage-head"><div class="eyebrow">Put it on the map</div><h1>Know a meeting?<br><em>Share the room.</em></h1><p>Help a neighbor find their way to a public meeting or community gathering. Please share accurate, publicly available event information.</p></header>
      <div id="create-message"></div>
      <form class="form-panel" id="create-form">
        <div class="form-grid">
          <div class="field full"><label for="event-title">Event title *</label><input id="event-title" name="title" required maxlength="180" placeholder="e.g. Eastside neighborhood plan listening session"></div>
          <div class="field"><label for="event-category">Category *</label><select id="event-category" name="category" required><option value="">Choose a category</option>${categoryOptions()}</select></div>
          <div class="field"><label for="event-organizer">Organizer *</label><input id="event-organizer" name="organizer" required maxlength="120" placeholder="Public body or group"></div>
           <div class="field"><label for="event-jurisdiction">Jurisdiction</label><select id="event-jurisdiction" name="jurisdiction">${["City","County","State","Federal"].map((j) => `<option value="${j}">${j}</option>`).join("")}</select></div>
           <div class="field"><label for="event-topics">Topics</label><input id="event-topics" name="topics" placeholder="Housing, transit, public comment"><small>Separate topics with commas.</small></div>
          <div class="field full"><label for="event-description">What should people know? *</label><textarea id="event-description" name="description" required maxlength="3000" placeholder="Agenda, who can attend, how to participate…"></textarea></div>
          <div class="field"><label for="event-location">Venue / address *</label><input id="event-location" name="location" required maxlength="180" placeholder="Building, room, or online details"></div>
          <div class="field"><label for="event-city">City or neighborhood *</label><input id="event-city" name="city" required maxlength="100" placeholder="Where is it happening?"></div>
           <div class="field"><label for="event-zip">ZIP code</label><input id="event-zip" name="zip_code" inputmode="numeric" pattern="[0-9]{5}(-[0-9]{4})?" maxlength="10" placeholder="e.g. 94102"></div>
           <div class="field"><label for="event-time">Date and time *</label><input id="event-time" name="starts_at" type="datetime-local" required></div>
           <div class="field"><label for="event-source">Organizer or source link (not checked)</label><input id="event-source" name="source_url" type="url" placeholder="https://…"><small>Community-submitted links are not verified by this app.</small></div>
            <div class="field"><label for="event-agenda">Agenda link (not checked)</label><input id="event-agenda" name="agenda_url" type="url" placeholder="https://…"></div>
          <div class="field full"><label for="event-accessibility">Accessibility information</label><textarea id="event-accessibility" name="accessibility" maxlength="1200" placeholder="Step-free access, interpretation, contact for accommodations…"></textarea></div>
        </div>
        <div class="form-footer"><p>After posting, you’ll receive an organizer check-in code. Keep it private and share it with attendees at the event.</p><button class="button-primary" type="submit">Post this event <span>↗</span></button></div>
      </form>
    </div>`;
  }

  function setMinDate() {
    const input = document.getElementById("event-time");
    if (input) input.min = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }

  function renderCreated(data) {
    const code = data.check_in_code;
    const event = data.event;
    const eventLink = event && event.id ? `/events/${encodeURIComponent(event.id)}` : "/";
    document.getElementById("create-message").innerHTML = `<section class="success-panel">
      <div class="eyebrow">Your listing is posted</div><h2>Thanks for opening the door.</h2>
      <p>${event ? `“${esc(event.title)}” is now listed for neighbors.` : "Your event is now listed for neighbors."} Here’s the organizer code for confirming attendance.</p>
      <div class="code-label">ORGANIZER CHECK-IN CODE</div>
      <div class="code-display"><strong>${esc(code || "Unavailable")}</strong><button type="button" id="copy-code" ${code ? "" : "disabled"}>Copy code</button></div>
      <p class="code-warning">Keep this code privately. Share it only with attendees at the event. Check-in is code-confirmed attendance; it does not verify a person’s identity.</p>
      <div class="empty-actions"><a class="button-primary" href="${eventLink}" data-link>View event <span>↗</span></a><a class="button-secondary" href="/" data-link>Back to calendar</a></div>
    </section>`;
    document.getElementById("create-form").remove();
    const copy = document.getElementById("copy-code");
    if (copy && code) copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(code); toast("Organizer code copied."); }
      catch { toast("Clipboard unavailable. Select and copy the code.", true); }
    });
  }

  async function submitCreate(form) {
    const button = form.querySelector('button[type="submit"]');
    const data = Object.fromEntries(new FormData(form).entries());
    data.topics = data.topics.split(",").map((topic) => topic.trim()).filter(Boolean);
    data.starts_at = new Date(data.starts_at).toISOString();
    button.disabled = true;
    button.textContent = "Posting…";
    document.getElementById("create-message").innerHTML = "";
    try {
      const result = await request("/api/events", { method: "POST", body: JSON.stringify(data) });
      renderCreated(result);
    } catch (error) {
      document.getElementById("create-message").innerHTML = `<div class="form-error" role="alert">${esc(error.message)}</div>`;
      button.disabled = false;
      button.innerHTML = "Post this event <span>↗</span>";
    }
  }

  function detailView() {
    return `<div class="page subpage" id="detail-holder">${skeleton()}</div>`;
  }

  async function loadDetail(id) {
    const holder = document.getElementById("detail-holder");
    if (!holder) return;
    try {
      const data = await request(`/api/events/${encodeURIComponent(id)}`);
      const event = data.event;
      if (!event) throw new Error("This event could not be found.");
        const officialLegistar = isOfficialLegistar(event);
        const attendanceOpen = Date.parse(event.starts_at) <= Date.now();
        const canSelfReport = officialLegistar && attendanceOpen && !event.is_cancelled;
       const topics = Array.isArray(event.topics) ? event.topics : [];
        const checked = ["verified_feed", "verified_site"].includes(event.source_status);
        const officialSf = String(event.source_provider || "").startsWith("legistar:sfgov:");
        const agendaItems = Array.isArray(data.agenda_items) ? data.agenda_items : [];
        const officialAgenda = officialSf ? `<section class="official-agenda" aria-labelledby="agenda-title">
          <h2 id="agenda-title">Official Agenda</h2>
          <p>${agendaItems.length ? `${agendaItems.length} items retrieved from the official meeting record.` : esc(data.agenda_error || "No agenda items are available from the official source yet.")}</p>
          <div class="agenda-list">${agendaItems.map((item) => `<article class="agenda-item">
            <div class="agenda-item-meta">${[
              item.agenda_number ? `Agenda ${esc(item.agenda_number)}` : "",
              item.file_number ? `File ${esc(item.file_number)}` : "",
              item.type ? esc(item.type) : "",
              item.status ? esc(item.status) : ""
            ].filter(Boolean).map((label) => `<span>${label}</span>`).join("")}</div>
            ${item.title ? `<h3>${esc(item.title)}</h3>` : ""}
            ${item.description ? `<p>${esc(item.description)}</p>` : ""}
          </article>`).join("")}</div>
        </section>` : "";
        const sourceBlock = event.source_url && !event.is_demo
          ? `<a class="button-secondary" href="${esc(event.source_url)}" target="_blank" rel="noopener noreferrer">${checked ? "Checked official meeting page" : "Submitted link · not checked"} ↗</a>`
          : `<span class="source-warning">${event.is_demo ? "Demo listing — no official source connected" : "No source link provided"}</span>`;
       const agendaBlock = event.agenda_url && !event.is_demo
          ? `<a class="button-secondary" href="${esc(event.agenda_url)}" target="_blank" rel="noopener noreferrer">${checked ? "Published agenda" : "Submitted agenda · not checked"} ↗</a>`
          : `<span class="source-warning">Agenda link unavailable</span>`;
       const ownerStart = new Date(new Date(event.starts_at).getTime() - new Date(event.starts_at).getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      holder.innerHTML = `<div class="detail-layout">
        <article class="detail-main">
          <a class="back-link" href="/" data-link>← Back to meetings</a>
           <div class="eyebrow">${esc(event.category || "Community event")} · ${esc(event.jurisdiction || "City")}</div>
           ${demoTag(event)}
          <h1>${esc(event.title)}</h1>
          <p class="detail-subline"><span>${esc(formatDate(event.starts_at, undefined, event.time_zone))}${formatTime(event.starts_at, event.time_zone) ? `, ${esc(formatTime(event.starts_at, event.time_zone))}` : ""}</span><span>${esc(event.city || "")}</span></p>
           <div class="topic-line">${topics.map((topic) => `<span>${esc(topic)}</span>`).join("")}</div>
          <p class="detail-description">${esc(event.description || "No event description was provided.")}</p>
           ${event.is_cancelled ? '<div class="notice" role="status">This event was cancelled. Existing RSVPs and Passport check-ins are preserved.</div>' : ""}
           ${event.is_mine && !event.is_cancelled ? `<details class="owner-tools"><summary>Manage your listing</summary><form id="owner-event-form" class="form-grid">
             <label class="field full">Title<input name="title" required maxlength="180" value="${esc(event.title)}"></label>
             <label class="field full">Description<textarea name="description" required maxlength="3000">${esc(event.description)}</textarea></label>
             <label class="field">Location<input name="location" required maxlength="180" value="${esc(event.location)}"></label>
             <label class="field">Date and time<input name="starts_at" type="datetime-local" required value="${esc(ownerStart)}"></label>
             <button class="button-primary" type="submit">Save listing</button>
           </form><div class="empty-actions"><button class="button-secondary" id="rotate-owner-code" type="button">Replace organizer code</button><button class="button-secondary" id="cancel-owner-event" type="button">Cancel event</button></div><div id="owner-message" role="status"></div></details>` : ""}
           <div class="detail-block"><h3>Where to go</h3><p>${esc(event.location || "Location details not provided")}</p></div>
            <div class="detail-block"><h3>Government body / organizer</h3><p>${esc(event.organizer || "Community organizer")}${officialSf && event.body_id ? ` · Legistar body ID ${esc(event.body_id)}` : ""}</p></div>
          ${event.accessibility ? `<div class="detail-block"><h3>Access & accommodations</h3><p>${esc(event.accessibility)}</p></div>` : ""}
            <div class="detail-block"><h3>Sources and planning</h3>${officialSf ? `<p>Data source: Official San Francisco Legistar ${event.source_provider?.endsWith(":official_site") ? "public website fallback (Events API unavailable)" : "Events API"}${event.agenda_status ? ` · Agenda status: ${esc(event.agenda_status)}` : ""}.</p>` : ""}<div class="source-actions">${sourceBlock}${agendaBlock}<button type="button" class="button-secondary" id="calendar-button">Add to Calendar ↗</button></div><p>${checked ? `Official record checked ${esc(formatDate(event.source_checked_at))}. This checks Legistar provenance, not every claim or change to the notice.` : "Links on community listings have not been verified. "} Always confirm times, agendas, and public-comment instructions with the official organizer.</p></div>
            ${officialAgenda}
            <section class="meeting-brief" id="brief-holder"><span class="demo-tag">BRIEFING PREVIEW · NOT AI-GENERATED</span><h2>What you need to know before attending</h2><p>This preview is based on the listing description, not a reviewed agenda. ${event.is_demo ? "This sample has no real agenda." : "Confirm the details using the linked organizer notice."}</p><div class="brief-grid"><div><h3>Meeting summary</h3><p>${esc(event.description)}</p></div><div><h3>Major topics</h3><p>${topics.length ? topics.map(esc).join(" · ") : "See the organizer’s agenda for confirmed topics."}</p></div><div><h3>Why residents may care</h3><p>Public meetings let residents learn about decisions in their community. This preview does not recommend a position.</p></div><div><h3>How to participate</h3><p>Check the organizer’s notice for public-comment instructions, access details, and registration requirements.</p></div></div><small>${checked ? "This is not an AI briefing. Request one below if an agenda and AI provider are available." : "No verified official-source citation is available for this listing."}</small>${checked && !event.is_cancelled ? '<p><button type="button" class="button-secondary" id="generate-brief">Request cited AI briefing ↗</button></p><div id="brief-message" role="status"></div>' : ""}</section>
        </article>
        <aside class="event-actions">
          <div class="action-label">MAKE A PLAN</div><h2>Are you going?</h2>
          ${event.is_cancelled
            ? '<p class="notice">This event has been cancelled. Participation history already recorded remains in your Passport.</p>'
            : `<p>Sign in to save this event to your account Passport.</p>
              <button type="button" class="button-primary" id="rsvp-button">I’m planning to go <span>↗</span></button>
               ${event.has_organizer_code ? '<button type="button" class="button-secondary" id="checkin-toggle" data-checkin-method="organizer_code">Check In</button>' : ""}
               ${canSelfReport ? '<button type="button" class="button-secondary" id="checkin-toggle" data-checkin-method="self_reported">Record Attendance</button>' : ""}
              <div class="rsvp-count" id="rsvp-count">${Number(event.rsvp_count || 0)} ${Number(event.rsvp_count || 0) === 1 ? "person" : "people"} planning to go</div>
               ${officialLegistar
                 ? `<p class="checkin-note">${attendanceOpen ? "This Passport entry is self-reported and not externally verified." : "Record Attendance becomes available after the meeting begins. This Passport entry is self-reported and not externally verified."}</p>`
                 : event.has_organizer_code
                   ? '<p class="checkin-note">Attendance requires the private organizer code. Code possession is not identity or government certification.</p>'
                   : ""}`}
        </aside>
      </div>`;
      bindDetail(event);
        request("/api/activity").then((activity) => {
         const button = document.getElementById("rsvp-button");
         if (button && activity.rsvps?.some((item) => item.id === event.id)) {
           button.dataset.going = "true";
           button.innerHTML = "You’re planning to go <span>✓</span>";
         }
       }).catch(() => {});
    } catch (error) {
      holder.innerHTML = `<div class="error-box"><span>${esc(error.message)}</span><button type="button" id="retry-detail">Try again</button></div>`;
      document.getElementById("retry-detail").addEventListener("click", () => loadDetail(id));
    }
  }

  function bindDetail(event) {
    const rsvpButton = document.getElementById("rsvp-button");
    const toggle = document.getElementById("checkin-toggle");
    const briefButton = document.getElementById("generate-brief");
    briefButton?.addEventListener("click", async () => {
      briefButton.disabled = true;
      const message = document.getElementById("brief-message");
      message.textContent = "Checking agenda items and generating a briefing…";
      try {
        const { brief } = await request(`/api/events/${encodeURIComponent(event.id)}/brief`, { method: "POST" });
        const fields = [["Meeting summary", brief.summary], ["Major topics", brief.topics], ["Why residents may care", brief.why_it_matters], ["How to participate", brief.participation]];
        document.getElementById("brief-holder").innerHTML = `<span class="demo-tag">${brief.mode === "band" ? "Multi-Agent Brief — Powered by Band" : brief.mode === "cached" ? "Cached AI Brief" : "Single-Agent Fallback"}</span><h2>What you need to know before attending</h2><p>Generated with ${esc(brief.model)} from retrieved official agenda titles${brief.agenda_scope ? ` (${esc(brief.agenda_scope.toLowerCase())})` : ""}. AI text may be incomplete or mistaken; verify details on the official page.</p>${briefStatus(brief, event)}<div class="brief-grid">${fields.map(([label, text]) => `<div><h3>${label}</h3><p>${esc(text)}</p></div>`).join("")}</div><h3>Agenda item citations</h3><ul>${brief.citations.map((c) => `<li><a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${brief.agenda_scope ? "Agenda row" : "Item"} ${esc(c.item_id)}: ${esc(c.title)} ↗</a></li>`).join("")}</ul><small>Official source last checked ${esc(formatDate(brief.source_checked_at))}. Citations identify agenda items, not independent fact-checking.</small>`;
      } catch (error) {
        message.textContent = error.message;
        briefButton.disabled = false;
      }
    });
    document.getElementById("calendar-button").addEventListener("click", () => {
      const start = new Date(event.starts_at);
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      const stamp = (date) => date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
      const clean = (value) => String(value || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
      const ics = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//GIT Civic//EN","BEGIN:VEVENT",`UID:${event.id}@git-civic`,`DTSTAMP:${stamp(new Date())}`,`DTSTART:${stamp(start)}`,`DTEND:${stamp(end)}`,`SUMMARY:${clean(event.title)}`,`LOCATION:${clean(event.location)}`,`DESCRIPTION:${clean(event.description)}`,"END:VEVENT","END:VCALENDAR"].join("\r\n");
      const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = "git-civic-event.ics"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    rsvpButton.addEventListener("click", async () => {
      const going = rsvpButton.dataset.going !== "true";
      rsvpButton.disabled = true;
      try {
        const result = await request(`/api/events/${encodeURIComponent(event.id)}/rsvp`, {
            method: "POST", body: JSON.stringify({ going })
        });
        rsvpButton.dataset.going = String(result.going);
        rsvpButton.innerHTML = result.going ? "You’re planning to go <span>✓</span>" : "I’m planning to go <span>↗</span>";
        document.getElementById("rsvp-count").textContent = `${Number(result.rsvp_count || 0)} ${Number(result.rsvp_count || 0) === 1 ? "person" : "people"} planning to go`;
        toast(result.going ? "Added to your activity." : "RSVP removed.");
      } catch (error) {
        toast(error.message, true);
      } finally { rsvpButton.disabled = false; }
    });
    document.getElementById("owner-event-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const values = Object.fromEntries(new FormData(e.currentTarget).entries());
      values.starts_at = new Date(values.starts_at).toISOString();
      try {
        await request(`/api/events/${encodeURIComponent(event.id)}`, { method: "PUT", body: JSON.stringify(values) });
        toast("Your listing was updated.");
        loadDetail(event.id);
      } catch (error) { document.getElementById("owner-message").textContent = error.message; }
    });
    document.getElementById("rotate-owner-code")?.addEventListener("click", async () => {
      if (!confirm("Replace the organizer code? The current code will stop working.")) return;
      try {
        const result = await request(`/api/events/${encodeURIComponent(event.id)}/organizer-code`, { method: "POST" });
        document.getElementById("owner-message").innerHTML = `<div class="notice success">New organizer code (shown once): <strong>${esc(result.check_in_code)}</strong>. Share privately with attendees.</div>`;
      } catch (error) { document.getElementById("owner-message").textContent = error.message; }
    });
    document.getElementById("cancel-owner-event")?.addEventListener("click", async () => {
      if (!confirm("Cancel this event? Existing RSVPs and Passport check-ins will be preserved.")) return;
      try {
        await request(`/api/events/${encodeURIComponent(event.id)}`, { method: "DELETE" });
        toast("Event cancelled. Participation history was preserved.");
        loadDetail(event.id);
      } catch (error) { document.getElementById("owner-message").textContent = error.message; }
    });
    toggle?.addEventListener("click", () => openCheckIn(event, toggle.dataset.checkinMethod));
  }

  function openCheckIn(event, method = "organizer_code") {
    const root = document.getElementById("modal-root");
    const selfReported = method === "self_reported";
    root.innerHTML = `<div class="modal-backdrop"><div class="verification-modal" role="dialog" aria-modal="true" aria-labelledby="verify-title"><button class="modal-close" id="close-modal" type="button" aria-label="Close">×</button><span class="eyebrow">Civic Passport</span><h2 id="verify-title">Record your participation</h2><p>${selfReported ? "This adds a Self Reported attendance entry. It is not externally verified." : "Enter the private organizer code shared at this event. This confirms code possession, not identity or government certification."}</p>
    <form id="verification-form">${selfReported ? '<button class="button-primary" type="submit">I attended — Record Attendance</button>' : '<label for="verification-code">Organizer code</label><input id="verification-code" name="code" autocomplete="off" required placeholder="Enter organizer code"><button class="button-primary" type="submit">Confirm code</button>'}</form><div id="verification-message" role="status"></div></div></div>`;
    const close = () => { root.innerHTML = ""; document.getElementById("checkin-toggle")?.focus(); };
    const confirm = async (method, code = "") => {
      const buttons = root.querySelectorAll("#verification-form button");
      buttons.forEach((button) => button.disabled = true);
      try {
        const result = await request(`/api/events/${encodeURIComponent(event.id)}/check-in`, {
          method: "POST", body: JSON.stringify(method === "self_reported" ? { method } : { code })
        });
        root.querySelector("#verification-message").innerHTML = `<div class="notice success">Participation added to your account Passport. <strong>${esc(verificationLabel(result.method || method))}</strong>. ${esc(verificationNote(result.method || method))} <a href="/passport" data-link>View Passport ↗</a></div>`;
        root.querySelector("#verification-form").hidden = true;
      } catch (error) {
        root.querySelector("#verification-message").textContent = error.message;
        root.querySelector("#verification-message").className = "form-error";
        buttons.forEach((button) => button.disabled = false);
      }
    };
    root.querySelector("#close-modal").addEventListener("click", close);
    root.querySelector(".modal-backdrop").addEventListener("click", (e) => { if (e.target.classList.contains("modal-backdrop")) close(); });
    root.querySelector("#verification-form").addEventListener("submit", (e) => {
      e.preventDefault();
      confirm(method, method === "self_reported" ? "" : root.querySelector("#verification-code").value.trim());
    });
    root.querySelector("#close-modal").focus();
  }

  function activityView() {
    return `<div class="page subpage" id="activity-holder">
      <div class="activity-top"><header class="subpage-head"><div class="eyebrow">Find it. Show up. Prove it.</div><h1>Civic <em>Passport.</em></h1><p>Your account-backed participation history, available when you sign in. Entries are not government-certified.</p></header><div class="passport-seal" aria-hidden="true">GIT<br>CIVIC<br><small>PARTICIPATION RECORD</small></div></div>
      <div class="passport-stats" id="activity-summary">${[1,2,3,4,5].map(() => `<div><strong>—</strong><span>Loading</span></div>`).join("")}</div>
      <div class="passport-toolbar"><button class="button-primary" id="export-resume" type="button">Export Civic Resume ↗</button><div class="privacy-control"><label for="privacy-select">Privacy</label><select id="privacy-select"><option value="Private">Private</option><option value="Public">Public Civic Resume</option></select></div></div>
      <p class="privacy-note" id="privacy-note">Private by default. Public sharing shows participation entries without receipts or account details.</p>
      <div id="share-passport"></div>
      <div id="activity-content">${skeleton()}</div>
      <section class="sample-passport"><span class="demo-tag">SAMPLE ACTIVITY · NOT YOUR RECORD</span><h2>A sample Civic Passport</h2><p>These example entries show what a participation timeline can look like. They are not your participation and do not count toward your totals.</p><div class="sample-timeline"><div><b>Neighborhood planning workshop</b><span>Self Reported · Demo example</span></div><div><b>Community transportation forum</b><span>Presence Verified · simulated demo example</span></div><div><b>Public school board meeting</b><span>Document Verified · simulated demo example</span></div></div><p><small>Officially Verified is a future evidence level, not available in this demo.</small></p></section>
    </div>`;
  }

  async function loadActivity() {
    const content = document.getElementById("activity-content");
    if (!content) return;
    try {
      const data = await request("/api/activity");
      const rsvps = Array.isArray(data.rsvps) ? data.rsvps : [];
      const checkIns = Array.isArray(data.check_ins) ? data.check_ins : [];
      const jurisdictions = new Set(checkIns.map((item) => item.event?.jurisdiction).filter(Boolean));
      const summaries = [
        [checkIns.length, "Total Civic Activities"], [checkIns.length, "Meetings Attended"],
        [0, "Public Comments"], [0, "Volunteer / Community Activities"],
        [jurisdictions.size, "Jurisdictions Participated In"]
      ];
      document.getElementById("activity-summary").innerHTML = summaries.map(([count, label]) => `<div><strong>${count}</strong><span>${label}</span></div>`).join("");
      const privacy = document.getElementById("privacy-select");
      if (privacy) privacy.value = data.public_passport ? "Public" : "Private";
      const privacyNote = document.getElementById("privacy-note");
      if (privacyNote) privacyNote.textContent = data.public_passport
        ? "Your Civic Resume is public. Anyone with its link can see your participation entries."
        : "Your Passport is private. Public sharing shows participation entries without receipts or account details.";
      const share = document.getElementById("share-passport");
      if (share) share.innerHTML = data.public_passport && data.share_slug
        ? `<div class="notice">Public link: <a href="/passport/share/${encodeURIComponent(data.share_slug)}" data-link>View your public Civic Resume ↗</a> <button type="button" id="copy-share-link">Copy link</button></div>`
        : "";
      document.getElementById("copy-share-link")?.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(`${location.origin}/passport/share/${data.share_slug}`); toast("Public link copied."); }
        catch { toast("Clipboard unavailable. Open the public link and copy it from the address bar.", true); }
      });
      const rsvpList = rsvps.length ? `<div class="results-grid">${rsvps.map((event) => eventRow(event)).join("")}</div>` : `<div class="activity-empty"><p>No saved events yet. Find a local event and make a plan to go.</p><a class="button-secondary" href="/" data-link>Discover events ↗</a></div>`;
      const checkedList = checkIns.length ? `<div class="passport-timeline">${checkIns.map((item) => `<article class="timeline-entry"><span class="timeline-date">${esc(formatDate(item.verified_at))}</span><div><a href="/events/${encodeURIComponent(item.event.id)}" data-link><h3>${esc(item.event.title)}</h3></a><p>${esc(item.event.city || "")} · ${esc(item.event.jurisdiction || "City")}</p><span class="evidence-badge">${esc(verificationLabel(item.method))}</span>${item.event.is_demo ? '<span class="demo-tag">DEMO EVENT</span>' : ""}<small>Receipt ${esc(item.receipt)} · ${esc(item.is_demo ? "Demo activity only." : verificationNote(item.method))}</small><button type="button" data-revoke-receipt="${esc(item.receipt)}">Remove from Passport</button></div></article>`).join("")}</div>` : `<div class="activity-empty"><p>No participation recorded yet. Open an event and record your attendance.</p><a class="button-secondary" href="/" data-link>Browse events ↗</a></div>`;
      const owned = data.owned_events || [];
      const ownedList = owned.length ? `<div class="results-grid">${owned.map((event) => `<div class="event-row">${eventRow(event)}<div class="empty-actions"><button type="button" data-owner-cancel="${esc(event.id)}" ${event.is_cancelled ? "disabled" : ""}>${event.is_cancelled ? "Cancelled" : "Cancel event"}</button><button type="button" data-owner-code="${esc(event.id)}" ${event.is_cancelled ? "disabled" : ""}>Replace code</button></div></div>`).join("")}</div>` : `<p>You have not posted any events yet.</p>`;
      content.innerHTML = `<section class="activity-section"><h2>Participation timeline</h2>${checkedList}</section><section class="activity-section"><h2>On your calendar</h2>${rsvpList}</section><section class="activity-section"><h2>Your event listings</h2>${ownedList}</section>`;
      content.querySelectorAll("[data-owner-cancel]").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("Cancel this event? Existing RSVPs and Passport check-ins will be preserved.")) return;
        try { await request(`/api/events/${encodeURIComponent(button.dataset.ownerCancel)}`, { method: "DELETE" }); loadActivity(); }
        catch (error) { toast(error.message, true); }
      }));
      content.querySelectorAll("[data-owner-code]").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("Replace the organizer code? The current code will stop working.")) return;
        try {
          const result = await request(`/api/events/${encodeURIComponent(button.dataset.ownerCode)}/organizer-code`, { method: "POST" });
          alert(`New organizer code (shown once): ${result.check_in_code}`);
        } catch (error) { toast(error.message, true); }
      }));
      content.querySelectorAll("[data-revoke-receipt]").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("Remove this check-in from your Civic Passport?")) return;
        try { await request(`/api/passport/check-ins/${encodeURIComponent(button.dataset.revokeReceipt)}`, { method: "DELETE" }); loadActivity(); }
        catch (error) { toast(error.message, true); }
      }));
      document.getElementById("export-resume").onclick = () => {
        const quote = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
        const rows = [["Event","Date","Jurisdiction","Evidence level","Receipt"], ...checkIns.map((item) => [item.event.title, item.verified_at, item.event.jurisdiction || "", verificationLabel(item.method), item.receipt])];
        const csv = rows.map((row) => row.map(quote).join(",")).join("\r\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        const link = document.createElement("a"); link.href = url; link.download = "git-civic-resume.csv"; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast("Civic Resume exported. Review evidence labels before sharing.");
      };
    } catch (error) {
      const unavailableStats = [
        "Total Civic Activities", "Meetings Attended", "Public Comments",
        "Volunteer / Community Activities", "Jurisdictions Participated In"
      ];
      const summary = document.getElementById("activity-summary");
      if (summary) {
        summary.innerHTML = unavailableStats
          .map((label) => `<div><strong>—</strong><span>${label}</span></div>`).join("");
      }
      const privacy = document.getElementById("privacy-select");
      if (privacy) privacy.disabled = true;
      const exportButton = document.getElementById("export-resume");
      if (exportButton) exportButton.disabled = true;
      const privacyNote = document.getElementById("privacy-note");
      if (privacyNote) {
        privacyNote.textContent = error.status === 401
          ? "Sign in to view your Passport entries and manage sharing."
          : "Passport data and privacy controls are unavailable until your history loads.";
      }
      content.innerHTML = `<div class="error-box"><span>We couldn’t load your participation history. ${esc(error.message)}</span><button type="button" id="retry-activity">Try again</button></div>`;
      document.getElementById("retry-activity").addEventListener("click", loadActivity);
    }
  }

  function infoView(kind) {
    const how = kind === "how";
    return `<div class="page subpage info-page"><header class="subpage-head"><div class="eyebrow">${how ? "The process" : "About GIT Civic"}</div><h1>${how ? "A better way to <em>show up.</em>" : "Get Involved <em>Today.</em>"}</h1><p>${how ? "Find it. Show up. Prove it. GIT Civic is a nonpartisan demonstration of a more accessible path into local public life." : "GIT Civic helps people discover public meetings, understand civic information in plain English, and keep an evidence-labeled record of participation."}</p></header>${how ? stageStrip() : `<div class="info-panel"><h2>Built for informed participation, not persuasion.</h2><p>We do not recommend candidates or political positions. Demo events are not live notices. Community-submitted links are not verified. Briefing previews are not AI-generated; cited AI briefs are only available for recently checked official-feed meetings when an AI provider is configured. Organizer codes confirm code possession, not identity or government certification.</p><p>The public Legistar feed supplies official meeting records. Account-backed Civic Passports are private by default, with optional public sharing. Confirm every meeting through the organizer before attending.</p></div>`}${intelligencePanel()}<a class="button-primary" href="/" data-link>Discover meetings ↗</a></div>`;
  }

  async function render() {
    const current = route();
    updateNav(current.name === "activity" ? "activity" : current.name === "home" ? "home" : "");
    if (current.name === "home") {
      app.innerHTML = homeView();
      document.getElementById("search-query").addEventListener("input", (e) => { state.query = e.target.value; });
      document.getElementById("search-category").addEventListener("change", (e) => { state.category = e.target.value; loadEvents(); });
      document.getElementById("search-jurisdiction").addEventListener("change", (e) => { state.jurisdiction = e.target.value; loadEvents(); });
      document.getElementById("search-form").addEventListener("submit", (e) => { e.preventDefault(); state.query = document.getElementById("search-query").value; loadEvents(); });
      await loadEvents();
    } else if (current.name === "new") {
      app.innerHTML = newView();
      setMinDate();
      document.getElementById("create-form").addEventListener("submit", (e) => { e.preventDefault(); submitCreate(e.currentTarget); });
    } else if (current.name === "detail") {
      app.innerHTML = detailView();
      await loadDetail(current.id);
    } else if (current.name === "activity") {
      app.innerHTML = activityView();
      const privacy = document.getElementById("privacy-select");
      privacy.addEventListener("change", async () => {
        try {
          await request("/api/account/privacy", { method: "PATCH", body: JSON.stringify({ public: privacy.value === "Public" }) });
          await loadActivity();
          toast(privacy.value === "Public" ? "Public Civic Resume enabled." : "Passport is private.");
        } catch (error) { privacy.value = privacy.value === "Public" ? "Private" : "Public"; toast(error.message, true); }
      });
      await loadActivity();
    } else if (current.name === "shared-passport") {
      app.innerHTML = `<div class="page subpage"><header class="subpage-head"><div class="eyebrow">Public Civic Resume</div><h1>Participation <em>record.</em></h1></header><div id="shared-activity">${skeleton()}</div></div>`;
      try {
        const data = await request(`/api/passport/shared/${encodeURIComponent(current.slug)}`);
        const entries = data.activities || [];
        document.getElementById("shared-activity").innerHTML = entries.length
          ? `<div class="passport-timeline">${entries.map((item) => `<article class="timeline-entry"><span class="timeline-date">${esc(formatDate(item.verified_at))}</span><div><h2>${esc(item.title)}</h2><p>${esc(item.city || "")} · ${esc(item.jurisdiction || "City")}</p><span class="evidence-badge">${esc(verificationLabel(item.method))}</span>${item.is_demo ? '<span class="demo-tag">DEMO</span>' : ""}</div></article>`).join("")}</div>`
          : `<p>No participation entries have been published on this Passport.</p>`;
      } catch (error) { document.getElementById("shared-activity").innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
    } else if (current.name === "how" || current.name === "about") {
      app.innerHTML = infoView(current.name);
    } else {
      app.innerHTML = `<div class="page subpage"><header class="subpage-head"><div class="eyebrow">Wrong turn</div><h1>This page<br><em>isn’t here.</em></h1><p>Head back to the neighborhood calendar to find what’s happening.</p><div class="empty-actions"><a class="button-primary" href="/" data-link>Back to meetings <span>↗</span></a></div></header></div>`;
    }
    app.focus({ preventScroll: true });
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-link]");
    if (link) {
      event.preventDefault();
      go(link.getAttribute("href"));
      return;
    }
    if (event.target.closest("#refresh-events, #retry-events")) loadEvents();
    if (event.target.closest("#clear-search")) {
      state.query = "";
      state.category = "";
      state.jurisdiction = "";
      render();
    }
  });
  menuToggle.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    menuToggle.setAttribute("aria-expanded", String(open));
  });
  window.addEventListener("popstate", render);
  let observedSignInState = null;
  window.addEventListener("git-civic-auth-changed", () => {
    const signedIn = Boolean(window.gitCivicAuth?.isSignedIn);
    if (observedSignInState !== null && observedSignInState !== signedIn && route().name === "activity") {
      loadActivity();
    }
    observedSignInState = signedIn;
  });
  render();
})();