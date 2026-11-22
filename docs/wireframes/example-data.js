// Illustrative records shared by the two interactive wireframes.
const exampleCitation = {doi: '10.0000/example.1', citation: 'Example imaging study, figure 1.'};

window.wireframeData = {
  source: {
    title: 'Example compartment catalogue', url: 'https://example.org/catalogue',
    sheet: 'Compartments', range: 'A1:F4', organism: 'Saccharomyces cerevisiae',
    modified_at: '2000-01-02T09:00:00Z', imported_on: '2000-01-03'
  },
  compartments: [
    {id: 'vacuole', name: 'Vacuole', priority: 1,
      description: 'A membrane surrounds the vacuolar lumen.', composition: 'Vacuolar fluid and a limiting membrane.',
      shape: 'Rounded in the example section.', microscopy_notes: 'The image panel can hold a schematic or micrograph.',
      references: [exampleCitation]},
    {id: 'nucleus', name: 'Nucleus', priority: 2,
      description: 'A compartment enclosed by the nuclear envelope.', composition: 'Chromatin and nucleoplasm.',
      overviews: [{overview_composition: 'Chromatin and nucleoplasm.',
        overview_structure: 'A double membrane surrounds the nucleus.',
        overview_shape: 'The outline can be round or elongated.'}],
      shape: '', microscopy_notes: '', references: []},
    {id: 'unmapped_structure', name: 'Unmapped structure', description: 'Example entry awaiting a term.',
      composition: '', shape: '', microscopy_notes: '', references: []}
  ],
  unassigned: [exampleCitation, {...exampleCitation, notes: 'Second entry for the same example DOI.'},
    {doi: '10.0000/example.2', citation: 'Example catalogue study.'}],
  papers: [
    {short: 'Imaging group', title: 'Cell morphology in a microscopy dataset', authors: 'Example imaging group',
      venue: 'Example journal', year: 2023, pid: 'imaging_2023', folder: 'papers/imaging_2023',
      doi: '10.0000/example.1', keywords: 'microscopy, cell shape', labels: ['Important', 'Imaging'],
      abstract: 'An example paper linking images to measurements of cell shape.', notes: 'Review the feature table.',
      other: [{name: 'README.md', path: '.', size: '2 KB'}], datasets: [
        {name: 'Cell images', description: 'Example collection of microscopy files.', role: 'describes',
          pid: 'urn:example:cell-images', folder: 'data/raw', format: 'OME-TIFF',
          files: [{name: 'field-01.ome.tif', path: 'data/raw', size: '1.2 MB', local: true}]},
        {name: 'Feature tables', description: 'Example image measurements.', role: 'derived',
          pid: 'urn:example:features', folder: 'data/output', format: 'TSV', source_datasets: ['urn:example:cell-images'],
          attributes: [{predicate: 'urn:example:property:pixel', display_label: 'Pixel size', value: '0.1', unit: 'µm'}],
          files: [{name: 'features.tsv', path: 'data/output', size: '4 KB', local: true},
            {name: 'additional.tsv', path: 'data/output', size: '2 KB', local: false}]}
      ]},
    {short: 'Survey group', title: 'A survey of cellular structures', authors: 'Example survey group',
      venue: 'Example journal', year: 2025, pid: 'survey_2025', folder: 'papers/survey_2025',
      doi: '10.0000/example.2', keywords: 'imaging, survey', labels: ['Imaging'],
      abstract: 'A second paper with an external image record.', notes: '', other: [], datasets: [
        {name: 'Survey images', description: 'An external image collection.', role: 'describes',
          pid: 'urn:example:survey', format: 'TIFF', source: 'https://example.org/survey',
          files: [{name: 'image.tif', path: 'image', size: '2 MB', local: false, external: true,
            url: 'https://example.org/survey/image.tif', preview_url: 'https://example.org/survey/preview',
            provider_url: 'https://example.org/survey'}]}
      ]}
  ]
};

// Illustrative methods for the version 5 browser. The older layouts use the records above.
window.wireframeMethods = {
  labels: {
    'urn:example:technique:brightfield': 'Brightfield microscopy',
    'urn:example:technique:outline': 'Outline tracing'
  },
  install(papers) {
    const [paper] = papers;
    const [images, tables] = paper.datasets;
    function method(familyID, family, typeID, type, id, value, annotations) {
      return {predicate: 'urn:example:methods', display_label: 'Methods', attributes: [
        {predicate: 'urn:example:method-family:' + familyID, display_label: family, attributes: [
          {predicate: 'urn:example:method-type:' + typeID, display_label: type, attributes: [
            {predicate: 'urn:example:technique', value, defined_by: 'urn:example:technique:' + id, annotations}
          ]}
        ]}
      ]};
    }
    const acquisition = method('experimental', 'Experimental', 'image-acquisition', 'Image acquisition',
      'brightfield', 'Transmitted-light imaging of a single field.', {
        status: 'reported', purpose: 'Record the cell outlines in this field.',
        inputs: [{label: 'Mounted sample'}], outputs: [{label: 'Field image', ref: 'field-01.ome.tif'}]
      });
    const trace = method('image-analysis', 'Image analysis', 'segmentation-annotation', 'Segmentation and annotation',
      'outline', 'Trace the boundary in the image.', {purpose: 'Measure the projected area.',
        inputs: [{label: 'Source images', ref: images.pid}], outputs: [{label: 'Feature table', ref: 'features.tsv'}]});
    paper.attributes = [{...acquisition, attributes: [...acquisition.attributes, ...trace.attributes]}];
    images.attributes = [acquisition, {predicate: 'urn:example:property:specimen', display_label: 'Specimen', attributes: [
      {predicate: 'urn:example:property:structure', display_label: 'Structure', value: 'vacuole'},
      {predicate: 'urn:example:property:structure-identifier', display_label: 'Structure identifier',
        value: 'http://purl.obolibrary.org/obo/GO_0005773'}
    ]}];
    images.files[0].attributes = [acquisition];
    tables.attributes.push(trace);
  }
};

window.wireframeFigures = {
  imaging_2023: {source: 'Example imaging study', figures: [
    {n: '1', title: 'Image measurements', caption: 'An example field and its measurement table.',
      panels: 'a–b', key: true, data: ['Cell images', 'Feature tables']},
    {n: '2', title: 'Field comparison', caption: 'Measurements across example fields.', panels: 'a–c'}
  ], samples: [{from: 'Fig. 1a', caption: 'Example image field', data: 'Cell images'}]}
};
