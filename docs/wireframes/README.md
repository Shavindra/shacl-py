# Viewer wireframes

[Dataset browser](dataset-browser.dc.html) is the version 6 design for Papers, Datasets, Compartments and file details.

The preview opens on the **Methods** tab of **Cell images**. Select **Brightfield microscopy** and **Vacuole** in the sidebar. Open the field image from **Outputs** to inspect its own method. The **Feature tables** dataset links back to the source images under **Inputs**. Both the paper and its datasets have a Methods tab. In Papers, open Figures to see the key figure and panel gallery. A related data link opens the dataset’s Files tab.

In **Compartments**, select **Nucleus** and expand **Notes** below the GO definition. The general overview stays visible when you switch organism tabs. The selection CSV supplies these fields.

| CSV column | Notes heading |
| --- | --- |
| `overview_composition` | Composition |
| `overview_structure` | Structure |
| `overview_shape` | Shape |

Select **Vacuole** to try two records for the same organism. Each has a numbered tab and a stable record ID. The **Overview** and **Raw metadata** tabs show the selected record.

[Earlier compartment browser](dataset-browser-before-organisms.dc.html) captures the layout before organism tabs. [Layout studies](layout-studies.dc.html) shows the earlier paper, dataset and file layouts.

To preview the wireframes, run this command from the repository root and open [the dataset browser](http://127.0.0.1:8080/dataset-browser.dc.html).

```sh
python -m http.server 8080 --bind 127.0.0.1 --directory docs/wireframes
```

The HTML files contain the editable layouts and interactions. They share [illustrative records](example-data.js). The preview loads its rendering libraries and fonts from public CDNs. The compartment design links to QuickGO.

For future design exports, update the corresponding HTML file in place and keep the shared examples. Git then shows which screens and interactions changed.
