(() => {
  "use strict";

  const search = document.querySelector("#catalog-search");
  const overview = document.querySelector("[data-overview-grid]");
  const visibleItems = document.querySelector("#visible-items");
  const visibleLabel = document.querySelector("#visible-label");
  const noResults = document.querySelector("#no-results");

  if (search && overview) {
    const cards = [...overview.querySelectorAll("[data-search-card]")];
    const singular = document.body.classList.contains("projects-overview")
      ? "project"
      : "creator";

    const filter = () => {
      const query = search.value.trim().toLocaleLowerCase();
      let count = 0;
      cards.forEach((card) => {
        const matches = (card.dataset.searchText || "").includes(query);
        card.hidden = !matches;
        if (matches) count += 1;
      });
      if (visibleItems) visibleItems.textContent = String(count);
      if (visibleLabel) visibleLabel.textContent = count === 1 ? singular : `${singular}s`;
      if (noResults) noResults.hidden = count !== 0;
    };

    search.addEventListener("input", filter);
    filter();
  }

  document.querySelectorAll(".content-row").forEach((row) => {
    const track = row.querySelector("[data-rail-track]");
    const previous = row.querySelector("[data-rail-previous]");
    const next = row.querySelector("[data-rail-next]");
    if (!track || !previous || !next) return;

    const update = () => {
      const maximum = Math.max(0, track.scrollWidth - track.clientWidth);
      previous.disabled = track.scrollLeft <= 2;
      next.disabled = track.scrollLeft >= maximum - 2;
      row.classList.toggle("is-scrollable", maximum > 2);
    };
    const move = (direction) => {
      track.scrollBy({ left: direction * track.clientWidth * 0.82, behavior: "smooth" });
    };

    previous.addEventListener("click", () => move(-1));
    next.addEventListener("click", () => move(1));
    track.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update, { passive: true });
    update();
  });

  const lightbox = document.querySelector("#media-lightbox");
  const viewer = document.querySelector("#lightbox-viewer");
  const playlist = document.querySelector("#audio-playlist");
  const title = document.querySelector("#lightbox-title");
  const original = document.querySelector("#lightbox-original");
  const previous = document.querySelector("[data-lightbox-previous]");
  const next = document.querySelector("[data-lightbox-next]");
  const closeButtons = document.querySelectorAll("[data-lightbox-close]");
  let items = [];
  let activeIndex = 0;
  let trigger = null;

  if (!lightbox || !viewer || !playlist || !title || !original || !previous || !next) {
    return;
  }

  const stopMedia = () => {
    viewer.querySelectorAll("audio, video").forEach((media) => {
      media.pause();
      media.removeAttribute("src");
      media.load();
    });
  };

  const groupItems = (group) =>
    [...document.querySelectorAll("[data-media-group]")].filter(
      (item) => item.dataset.mediaGroup === group,
    );

  const renderPlaylist = () => {
    playlist.replaceChildren();
    items.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.dataset.mediaTitle || "Audio";
      button.className = index === activeIndex ? "current" : "";
      button.addEventListener("click", () => show(index, true));
      playlist.append(button);
    });
  };

  const show = (index, autoplay = false) => {
    stopMedia();
    activeIndex = (index + items.length) % items.length;
    const item = items[activeIndex];
    const kind = item.dataset.mediaKind;
    const source = item.dataset.mediaSrc || "";
    const itemTitle = item.dataset.mediaTitle || "Media";
    title.textContent = itemTitle;
    original.href = source;
    viewer.replaceChildren();
    playlist.hidden = kind !== "audio";

    let media;
    if (kind === "image") {
      media = document.createElement("img");
      media.src = source;
      media.alt = itemTitle;
    } else if (kind === "pdf") {
      media = document.createElement("iframe");
      media.src = source;
      media.title = itemTitle;
    } else if (kind === "video") {
      media = document.createElement("video");
      media.src = source;
      media.controls = true;
      media.preload = "metadata";
      if (item.dataset.poster) media.poster = item.dataset.poster;
    } else if (kind === "audio") {
      media = document.createElement("audio");
      media.src = source;
      media.controls = true;
      media.preload = "metadata";
      media.addEventListener("ended", () => {
        if (activeIndex < items.length - 1) show(activeIndex + 1, true);
      });
      renderPlaylist();
    }

    if (media) {
      viewer.append(media);
      if (autoplay && "play" in media) media.play().catch(() => {});
    }
    previous.disabled = items.length < 2;
    next.disabled = items.length < 2;
  };

  const open = (item) => {
    trigger = item;
    items = groupItems(item.dataset.mediaGroup || "");
    activeIndex = Math.max(0, items.indexOf(item));
    lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
    show(activeIndex, item.dataset.mediaKind === "audio");
    lightbox.querySelector("[data-lightbox-close]")?.focus();
  };

  const close = () => {
    stopMedia();
    lightbox.hidden = true;
    document.body.classList.remove("lightbox-open");
    viewer.replaceChildren();
    playlist.replaceChildren();
    trigger?.focus();
  };

  document.querySelectorAll("[data-media-kind]").forEach((item) => {
    item.addEventListener("click", () => open(item));
  });
  previous.addEventListener("click", () => show(activeIndex - 1, true));
  next.addEventListener("click", () => show(activeIndex + 1, true));
  closeButtons.forEach((button) => button.addEventListener("click", close));
  document.addEventListener("keydown", (event) => {
    if (lightbox.hidden) return;
    if (event.key === "Escape") close();
    if (event.key === "ArrowLeft") show(activeIndex - 1, true);
    if (event.key === "ArrowRight") show(activeIndex + 1, true);
  });
})();
