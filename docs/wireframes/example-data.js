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
