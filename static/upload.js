(function () {
  const form      = document.getElementById("generate-form");
  const fileInput = document.getElementById("photo");
  const pathField = document.getElementById("photo_pathname");
  const status    = document.getElementById("upload-status");
  const submitBtn = document.getElementById("submit-btn");

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

  form.addEventListener("submit", function (event) {
    if (pathField.value) return; // already uploaded — let the real submit through

    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) {
      status.textContent = "Please choose a photograph first.";
      return;
    }

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
