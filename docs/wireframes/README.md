# Viewer wireframes

[Dataset browser](dataset-browser.dc.html) is the version 4 design for Papers, Datasets, Compartments and record details. It uses sentence case for section and table headings, with light dividers above attribute, image and reference lists.

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
