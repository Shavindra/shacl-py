// A local image preview for the wireframes. Dropped files stay in the browser tab.
if (!customElements.get('image-slot')) {
  customElements.define('image-slot', class extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      const root = this.attachShadow({mode: 'open'});
      root.innerHTML = `<style>
        :host{display:grid;width:100%;height:100%;place-items:center;color:#777;font:13px sans-serif}
        label{display:grid;width:100%;height:100%;place-items:center;cursor:pointer}
        input{position:absolute;width:1px;height:1px;opacity:0}label:focus-within{outline:2px solid}
        img{width:100%;height:100%;object-fit:contain;min-height:0} [hidden]{display:none}
      </style><label><input type="file" accept="image/*"><span></span><img hidden></label>`;
      const input = root.querySelector('input');
      const caption = root.querySelector('span');
      const image = root.querySelector('img');
      caption.textContent = this.getAttribute('placeholder') || 'Choose image';
      input.setAttribute('aria-label', caption.textContent);
      const preview = file => {
        if (!file || !file.type.startsWith('image/')) return;
        if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
        this.previewUrl = URL.createObjectURL(file);
        image.src = this.previewUrl;
        image.alt = file.name;
        image.hidden = false;
        caption.hidden = true;
      };
      input.addEventListener('change', () => preview(input.files[0]));
      this.addEventListener('dragover', event => event.preventDefault());
      this.addEventListener('drop', event => {
        event.preventDefault();
        preview(event.dataTransfer.files[0]);
      });
    }
    disconnectedCallback() {
      if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
    }
  });
}
