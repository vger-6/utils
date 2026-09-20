(() => {
  "use strict";

  const creatorList = document.querySelector("#creator-list");
  const search = document.querySelector("#catalog-search");
  const visibleCreators = document.querySelector("#visible-creators");
  const visibleProjects = document.querySelector("#visible-projects");
  const creatorLabel = document.querySelector("#creator-label");
  const projectLabel = document.querySelector("#project-label");
  const noResults = document.querySelector("#no-results");

  if (!creatorList || !search) {
    return;
  }

  const filter = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let creatorCount = 0;
    let projectCount = 0;

    creatorList.querySelectorAll(".creator-section").forEach((section) => {
      const creatorName = (section.dataset.creatorName || "").toLocaleLowerCase();
      const creatorMatches = creatorName.includes(query);
      let matchingProjects = 0;

      section.querySelectorAll(".project-card").forEach((card) => {
        const projectName = (card.dataset.projectName || "").toLocaleLowerCase();
        const matches = !query || creatorMatches || projectName.includes(query);
        card.hidden = !matches;
        if (matches) {
          matchingProjects += 1;
        }
      });

      section.hidden = matchingProjects === 0;
      if (!section.hidden) {
        creatorCount += 1;
        projectCount += matchingProjects;
      }
    });

    if (visibleCreators) visibleCreators.textContent = String(creatorCount);
    if (visibleProjects) visibleProjects.textContent = String(projectCount);
    if (creatorLabel) creatorLabel.textContent = creatorCount === 1 ? "creator" : "creators";
    if (projectLabel) projectLabel.textContent = projectCount === 1 ? "project" : "projects";
    if (noResults) noResults.hidden = creatorCount !== 0;
  };

  search.addEventListener("input", filter);
  filter();
})();
