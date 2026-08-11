(function () {
  const form        = document.getElementById("generate-form");
  const fileInput   = document.getElementById("photo");
  const pathField   = document.getElementById("photo_pathname");
  const status      = document.getElementById("upload-status");
  const submitBtn   = document.getElementById("submit-btn");
  const errorBox    = document.getElementById("client-error");
  const bottomText  = document.getElementById("bottom_text");
  const filenameFld = document.getElementById("filename");

  // photo_pathname can arrive pre-filled (server re-renders it after a
  // generation so the whole form stays sticky — see issue #25). Picking a
  // new file means the old pathname no longer applies, so drop it and let
  // the submit handler's normal "not yet uploaded" path re-upload for real.
  fileInput.addEventListener("change", function () {
    pathField.value = "";
    status.textContent = "";
  });

  // Direct-to-Blob upload: bypasses this app's Function entirely, so the
  // 4.5MB Vercel Function body-size cap never applies to the photo itself.
  // See api/blob-upload.ts for the presigned-URL half of this.
  async function uploadPhoto(file) {
    const tokenResp = await fetch("/api/blob-upload", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ contentType: file.type }),
    });
    if (!tokenResp.ok) {
      const err = await tokenResp.json().catch(() => ({}));
      throw new Error(err.error || "Could not prepare the upload.");
    }
    const { presignedUrl, pathname } = await tokenResp.json();

    const putResp = await fetch(presignedUrl, {
      method: "PUT",
      body: file,
      headers: { "content-type": file.type },
    });
    if (!putResp.ok) {
      throw new Error("Uploading the photo failed. Please try again.");
    }
    return pathname;
  }

  // Required to generate: a photo (already uploaded, or picked just now)
  // and either a bottom text or a "Save as" filename (mirrors /generate's
  // own server-side check — this just catches it before a round trip).
  function missingRequirements() {
    const missing = [];
    if (!pathField.value && !fileInput.files[0]) missing.push("a photograph");
    if (!bottomText.value.trim() && !filenameFld.value.trim()) {
      missing.push('a bottom text (or a "Save as" filename)');
    }
    return missing;
  }

  // Best-effort: if a result is closed/navigated away from without being
  // downloaded, tell the server to reclaim its Blob storage rather than
  // waiting on the daily cleanup cron. A plain <a> download doesn't unload
  // the page, so this doesn't fire on the download click itself; if it
  // fires anyway, the abandon route safely finds nothing left to delete.
  // `pagehide` is used over `beforeunload`, which is unreliable
  // (especially on mobile) and blocks the back/forward cache.
  const downloadsCard = document.querySelector(".downloads-card[data-abandon-url]");
  if (downloadsCard) {
    window.addEventListener("pagehide", function () {
      navigator.sendBeacon(downloadsCard.dataset.abandonUrl);
    });
  }

  form.addEventListener("submit", function (event) {
    const missing = missingRequirements();
    if (missing.length) {
      event.preventDefault();
      errorBox.hidden = false;
      errorBox.textContent = "Please add " + missing.join(" and ") + " before generating.";
      return;
    }
    errorBox.hidden = true;

    if (pathField.value) return; // already uploaded — let the real submit through

    event.preventDefault();
    const file = fileInput.files[0];

    submitBtn.disabled = true;
    status.textContent = "Uploading photo…";

    uploadPhoto(file)
      .then(function (pathname) {
        pathField.value = pathname;
        status.textContent = "Uploaded. Generating…";
        form.requestSubmit();
      })
      .catch(function (err) {
        status.textContent = err.message || "Upload failed. Please try again.";
        submitBtn.disabled = false;
      });
  });
})();
