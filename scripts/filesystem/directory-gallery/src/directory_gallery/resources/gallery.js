(() => {
  "use strict";

  const parseData = (element) => {
    if (!element) return [];
    try {
      const value = JSON.parse(element.textContent || "[]");
      return Array.isArray(value) ? value : [];
    } catch (_error) {
      return [];
    }
  };

  const artwork = (item, frameClass) => {
    const frame = document.createElement("span");
    frame.className = frameClass;
    if (item.image) {
      const image = document.createElement("img");
      image.src = item.image;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      frame.append(image);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "image-placeholder media-placeholder";
      placeholder.ariaHidden = "true";
      const label = document.createElement("span");
      label.textContent = item.placeholder || "?";
      placeholder.append(label);
      frame.append(placeholder);
    }
    return frame;
  };

  const overview = document.querySelector("[data-overview-grid]");
  const overviewData = parseData(document.querySelector("#overview-data"));
  const search = document.querySelector("#catalog-search");
  const visibleItems = document.querySelector("#visible-items");
  const visibleLabel = document.querySelector("#visible-label");
  const noResults = document.querySelector("#no-results");
  const pagination = document.querySelector("[data-pagination]");
  const pagePrevious = document.querySelector("[data-page-previous]");
  const pageNext = document.querySelector("[data-page-next]");
  const pageStatus = document.querySelector("[data-page-status]");

  if (overview && search && pagination && pagePrevious && pageNext && pageStatus) {
    const kind = overview.dataset.cardKind || "creator";
    const singular = kind === "project" ? "project" : "creator";
    const batchSize = 120;
    let initial = "";
    let filtered = overviewData;
    let currentPage = 0;
    let searchTimer;

    const createOverviewCard = (item) => {
      const card = document.createElement("a");
      card.className = `overview-card ${kind}-overview-card`;
      card.href = item.href;
      const frameClass =
        kind === "creator"
          ? "overview-artwork portrait-frame"
          : "project-artwork cover-frame";
      card.append(artwork(item, frameClass));

      const copy = document.createElement("span");
      copy.className = "overview-copy";
      const title = document.createElement("span");
      title.className = "overview-title";
      title.textContent = item.title;
      const meta = document.createElement("span");
      meta.className = "overview-meta";
      meta.textContent = item.meta;
      copy.append(title, meta);
      card.append(copy);
      return card;
    };

    const renderPage = () => {
      overview.replaceChildren();
      const fragment = document.createDocumentFragment();
      const pageCount = Math.max(1, Math.ceil(filtered.length / batchSize));
      currentPage = Math.min(currentPage, pageCount - 1);
      const start = currentPage * batchSize;
      const limit = Math.min(filtered.length, start + batchSize);
      for (let index = start; index < limit; index += 1) {
        fragment.append(createOverviewCard(filtered[index]));
      }
      overview.append(fragment);
      pagination.hidden = pageCount <= 1;
      pagePrevious.disabled = currentPage === 0;
      pageNext.disabled = currentPage >= pageCount - 1;
      pageStatus.textContent = `Page ${currentPage + 1} of ${pageCount}`;
    };

    const applyFilter = () => {
      const query = search.value.trim().toLocaleLowerCase();
      filtered = overviewData.filter(
        (item) =>
          (!initial || item.initial === initial) &&
          (!query || (item.search || "").includes(query)),
      );
      currentPage = 0;
      renderPage();
      if (visibleItems) visibleItems.textContent = String(filtered.length);
      if (visibleLabel) {
        visibleLabel.textContent = filtered.length === 1 ? singular : `${singular}s`;
      }
      if (noResults) noResults.hidden = filtered.length !== 0;
    };

    search.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(applyFilter, 100);
    });
    document.querySelectorAll("[data-initial]").forEach((button) => {
      button.addEventListener("click", () => {
        initial = button.dataset.initial || "";
        document.querySelectorAll("[data-initial]").forEach((candidate) => {
          candidate.classList.toggle("current", candidate === button);
        });
        applyFilter();
      });
    });
    pagePrevious.addEventListener("click", () => {
      currentPage -= 1;
      renderPage();
      overview.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    pageNext.addEventListener("click", () => {
      currentPage += 1;
      renderPage();
      overview.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    applyFilter();
  }

  const lightbox = document.querySelector("#media-lightbox");
  const viewer = document.querySelector("#lightbox-viewer");
  const playlist = document.querySelector("#audio-playlist");
  const lightboxTitle = document.querySelector("#lightbox-title");
  const original = document.querySelector("#lightbox-original");
  const lightboxPrevious = document.querySelector("[data-lightbox-previous]");
  const lightboxNext = document.querySelector("[data-lightbox-next]");
  const closeButtons = document.querySelectorAll("[data-lightbox-close]");
  let activeItems = [];
  let activeIndex = 0;
  let trigger = null;

  const stopMedia = () => {
    viewer?.querySelectorAll("audio, video").forEach((media) => {
      media.pause();
      media.removeAttribute("src");
      media.load();
    });
  };

  const renderPlaylist = () => {
    if (!playlist) return;
    playlist.replaceChildren();
    activeItems.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.title || "Audio";
      button.className = index === activeIndex ? "current" : "";
      button.addEventListener("click", () => showMedia(index, true));
      playlist.append(button);
    });
  };

  const showMedia = (index, autoplay = false) => {
    if (
      !viewer ||
      !playlist ||
      !lightboxTitle ||
      !original ||
      !lightboxPrevious ||
      !lightboxNext ||
      activeItems.length === 0
    ) {
      return;
    }
    stopMedia();
    activeIndex = (index + activeItems.length) % activeItems.length;
    const item = activeItems[activeIndex];
    lightboxTitle.textContent = item.title || "Media";
    original.href = item.src || "";
    viewer.replaceChildren();
    playlist.hidden = item.kind !== "audio";

    let media;
    if (item.kind === "image") {
      media = document.createElement("img");
      media.src = item.src;
      media.alt = item.title || "";
    } else if (item.kind === "pdf") {
      media = document.createElement("iframe");
      media.src = item.src;
      media.title = item.title || "PDF";
    } else if (item.kind === "video") {
      media = document.createElement("video");
      media.src = item.src;
      media.controls = true;
      media.preload = "metadata";
      if (item.poster) media.poster = item.poster;
    } else if (item.kind === "audio") {
      media = document.createElement("audio");
      media.src = item.src;
      media.controls = true;
      media.preload = "metadata";
      media.addEventListener("ended", () => {
        if (activeIndex < activeItems.length - 1) showMedia(activeIndex + 1, true);
      });
      renderPlaylist();
    }

    if (media) {
      viewer.append(media);
      if (autoplay && "play" in media) media.play().catch(() => {});
    }
    lightboxPrevious.disabled = activeItems.length < 2;
    lightboxNext.disabled = activeItems.length < 2;
  };

  const openLightbox = (items, index, button) => {
    if (!lightbox) return;
    activeItems = items;
    activeIndex = index;
    trigger = button;
    lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
    showMedia(index, items[index]?.kind === "audio");
    lightbox.querySelector("[data-lightbox-close]")?.focus();
  };

  const closeLightbox = () => {
    if (!lightbox || !viewer || !playlist) return;
    stopMedia();
    lightbox.hidden = true;
    document.body.classList.remove("lightbox-open");
    viewer.replaceChildren();
    playlist.replaceChildren();
    trigger?.focus();
  };

  const createRailCard = (item, items, index) => {
    if (item.kind === "project") {
      const card = document.createElement("a");
      card.className = "project-card";
      card.href = item.href;
      card.append(artwork(item, "project-artwork cover-frame"));
      const copy = document.createElement("span");
      copy.className = "overview-copy";
      const title = document.createElement("span");
      title.className = "overview-title";
      title.textContent = item.title;
      copy.append(title);
      card.append(copy);
      return card;
    }

    const card = document.createElement("button");
    card.type = "button";
    card.className = `media-card ${item.kind}-card`;
    card.append(artwork(item, "media-artwork"));
    const title = document.createElement("span");
    title.className = "media-title";
    title.textContent = item.title;
    card.append(title);
    card.addEventListener("click", () => openLightbox(items, index, card));
    return card;
  };

  const activeRailUpdates = new Set();

  const initializeRail = (row) => {
    if (row.dataset.railReady === "true") return;
    const track = row.querySelector("[data-rail-track]");
    const canvas = row.querySelector("[data-rail-canvas]");
    const data = Array.isArray(row._railData)
      ? row._railData
      : parseData(row.querySelector("[data-rail-data]"));
    const previous = row.querySelector("[data-rail-previous]");
    const next = row.querySelector("[data-rail-next]");
    if (!track || !canvas || !previous || !next) return;
    row.dataset.railReady = "true";
    const rendered = new Map();

    const dimensions = () => {
      const styles = getComputedStyle(track);
      return {
        width: Number.parseFloat(styles.getPropertyValue("--rail-card-width")) || 180,
        gap: Number.parseFloat(styles.getPropertyValue("--rail-gap")) || 16,
      };
    };

    const update = () => {
      const { width, gap } = dimensions();
      const step = width + gap;
      canvas.style.width = `${Math.max(0, data.length * step - gap)}px`;
      const start = Math.max(0, Math.floor(track.scrollLeft / step) - 5);
      const end = Math.min(
        data.length,
        Math.ceil((track.scrollLeft + track.clientWidth) / step) + 5,
      );

      rendered.forEach((card, index) => {
        if (index < start || index >= end) {
          card.remove();
          rendered.delete(index);
        }
      });
      for (let index = start; index < end; index += 1) {
        if (rendered.has(index)) continue;
        const card = createRailCard(data[index], data, index);
        card.classList.add("virtual-card");
        card.style.left = `${index * step}px`;
        card.style.width = `${width}px`;
        canvas.append(card);
        rendered.set(index, card);
      }

      const maximum = Math.max(0, track.scrollWidth - track.clientWidth);
      previous.disabled = track.scrollLeft <= 2;
      next.disabled = track.scrollLeft >= maximum - 2;
      row.classList.toggle("is-scrollable", maximum > 2);
    };

    const move = (direction) => {
      track.scrollBy({ left: direction * track.clientWidth * 0.82, behavior: "smooth" });
    };
    const movePrevious = () => move(-1);
    const moveNext = () => move(1);
    previous.addEventListener("click", movePrevious);
    next.addEventListener("click", moveNext);
    track.addEventListener("scroll", update, { passive: true });
    activeRailUpdates.add(update);
    row._destroyRail = () => {
      previous.removeEventListener("click", movePrevious);
      next.removeEventListener("click", moveNext);
      track.removeEventListener("scroll", update);
      activeRailUpdates.delete(update);
    };
    update();
  };

  const initializeRails = (scope) => {
    scope.querySelectorAll(".content-row").forEach(initializeRail);
  };

  const destroyRails = (scope) => {
    scope.querySelectorAll(".content-row").forEach((row) => row._destroyRail?.());
  };

  window.addEventListener(
    "resize",
    () => activeRailUpdates.forEach((update) => update()),
    { passive: true },
  );
  initializeRails(document);

  const createProjectRail = (projects) => {
    const row = document.createElement("section");
    row.className = "content-row project-row grouped-project-row";
    row.dataset.contentKind = "project";
    row._railData = projects;

    const heading = document.createElement("div");
    heading.className = "row-heading";
    const title = document.createElement("h3");
    title.textContent = "Projects";
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const previous = document.createElement("button");
    previous.type = "button";
    previous.dataset.railPrevious = "";
      previous.setAttribute("aria-label", "Scroll projects left");
    previous.textContent = "‹";
    const next = document.createElement("button");
    next.type = "button";
    next.dataset.railNext = "";
      next.setAttribute("aria-label", "Scroll projects right");
    next.textContent = "›";
    actions.append(previous, next);
    heading.append(title, actions);

    const track = document.createElement("div");
    track.className = "rail-track";
    track.dataset.railTrack = "";
    const canvas = document.createElement("div");
    canvas.className = "rail-canvas";
    canvas.dataset.railCanvas = "";
    track.append(canvas);
    row.append(heading, track);
    return row;
  };

  const createGroupedCreator = (item, projects) => {
    const section = document.createElement("section");
    section.className = "grouped-creator";
    const header = document.createElement("header");
    header.className = "grouped-creator-header";

    if (item.image) {
      const portraitLink = document.createElement("a");
      portraitLink.className = "grouped-portrait-link";
      portraitLink.href = item.href;
      portraitLink.setAttribute("aria-label", item.title);
      portraitLink.append(artwork(item, "grouped-portrait-artwork portrait-frame"));
      header.append(portraitLink);
    }

    const copy = document.createElement("div");
    copy.className = "grouped-creator-copy";
    const title = document.createElement("h2");
    const link = document.createElement("a");
    link.href = item.href;
    link.textContent = item.title;
    title.append(link);
    const meta = document.createElement("p");
    meta.className = "overview-meta";
    meta.textContent = `${projects.length} ${projects.length === 1 ? "project" : "projects"}`;
    copy.append(title, meta);
    header.append(copy);
    section.append(header);

    if (projects.length) {
      section.append(createProjectRail(projects));
    } else {
      const empty = document.createElement("p");
      empty.className = "grouped-empty";
      empty.textContent = "No projects.";
      section.append(empty);
    }
    return section;
  };

  const groupedList = document.querySelector("[data-grouped-list]");
  const groupedData = parseData(document.querySelector("#grouped-data"));
  const groupedPagination = document.querySelector("[data-grouped-pagination]");
  const groupedPrevious = document.querySelector("[data-grouped-previous]");
  const groupedNext = document.querySelector("[data-grouped-next]");
  const groupedStatus = document.querySelector("[data-grouped-status]");
  const visibleProjects = document.querySelector("#visible-projects");
  const visibleProjectLabel = document.querySelector("#visible-project-label");

  if (
    groupedList &&
    search &&
    groupedPagination &&
    groupedPrevious &&
    groupedNext &&
    groupedStatus
  ) {
    const batchSize = 40;
    let initial = "";
    let filtered = [];
    let currentPage = 0;
    let searchTimer;

    const renderGroupedPage = () => {
      destroyRails(groupedList);
      groupedList.replaceChildren();
      const fragment = document.createDocumentFragment();
      const pageCount = Math.max(1, Math.ceil(filtered.length / batchSize));
      currentPage = Math.min(currentPage, pageCount - 1);
      const start = currentPage * batchSize;
      const limit = Math.min(filtered.length, start + batchSize);
      for (let index = start; index < limit; index += 1) {
        const entry = filtered[index];
        fragment.append(createGroupedCreator(entry.item, entry.projects));
      }
      groupedList.append(fragment);
      initializeRails(groupedList);
      groupedPagination.hidden = pageCount <= 1;
      groupedPrevious.disabled = currentPage === 0;
      groupedNext.disabled = currentPage >= pageCount - 1;
      groupedStatus.textContent = `Page ${currentPage + 1} of ${pageCount}`;
    };

    const applyGroupedFilter = () => {
      const query = search.value.trim().toLocaleLowerCase();
      filtered = groupedData.flatMap((item) => {
        if (initial && item.initial !== initial) return [];
        const allProjects = Array.isArray(item.projects) ? item.projects : [];
        const creatorMatches = !query || (item.search || "").includes(query);
        const projects = creatorMatches
          ? allProjects
          : allProjects.filter((project) =>
              (project.search || "").includes(query),
            );
        if (!creatorMatches && projects.length === 0) return [];
        return [{ item, projects }];
      });
      currentPage = 0;
      renderGroupedPage();

      const projectCount = filtered.reduce(
        (count, entry) => count + entry.projects.length,
        0,
      );
      if (visibleItems) visibleItems.textContent = String(filtered.length);
      if (visibleLabel) {
        visibleLabel.textContent = filtered.length === 1 ? "creator" : "creators";
      }
      if (visibleProjects) visibleProjects.textContent = String(projectCount);
      if (visibleProjectLabel) {
        visibleProjectLabel.textContent = projectCount === 1 ? "project" : "projects";
      }
      if (noResults) noResults.hidden = filtered.length !== 0;
    };

    search.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(applyGroupedFilter, 100);
    });
    document.querySelectorAll("[data-initial]").forEach((button) => {
      button.addEventListener("click", () => {
        initial = button.dataset.initial || "";
        document.querySelectorAll("[data-initial]").forEach((candidate) => {
          candidate.classList.toggle("current", candidate === button);
        });
        applyGroupedFilter();
      });
    });
    groupedPrevious.addEventListener("click", () => {
      currentPage -= 1;
      renderGroupedPage();
      groupedList.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    groupedNext.addEventListener("click", () => {
      currentPage += 1;
      renderGroupedPage();
      groupedList.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    applyGroupedFilter();
  }

  lightboxPrevious?.addEventListener("click", () => showMedia(activeIndex - 1, true));
  lightboxNext?.addEventListener("click", () => showMedia(activeIndex + 1, true));
  closeButtons.forEach((button) => button.addEventListener("click", closeLightbox));
  document.addEventListener("keydown", (event) => {
    if (!lightbox || lightbox.hidden) return;
    if (event.key === "Escape") closeLightbox();
    if (event.key === "ArrowLeft") showMedia(activeIndex - 1, true);
    if (event.key === "ArrowRight") showMedia(activeIndex + 1, true);
  });
})();
