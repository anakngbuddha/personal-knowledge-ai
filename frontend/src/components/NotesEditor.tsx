// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { request } from '../services/http';
import './NotesEditor.css';

interface Note {
  id: string;
  title: string;
  slug: string;
  body: string;
  workspace_id: string;
  created_at: string | null;
  updated_at: string | null;
  links: NoteLinkOut[];
}

interface NoteLinkOut {
  target_kind: string;
  target_ref: string;
  display_text: string | null;
  resolved: boolean;
  resolved_id: string | null;
}

interface LinkTarget {
  kind: string;
  ref: string;
  title: string;
}

interface GraphNode {
  id: string;
  kind: string;
  title: string;
  slug: string;
}

interface GraphEdge {
  source_id: string;
  source_kind: string;
  target_id: string;
  target_kind: string;
  target_ref: string;
  display_text: string | null;
  resolved: boolean;
}

interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

type ViewMode = 'editor' | 'graph' | 'backlinks';

export const NotesEditor: React.FC = () => {
  const [viewMode, setViewMode] = useState<ViewMode>('editor');
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [editingBody, setEditingBody] = useState('');
  const [linkSuggestions, setLinkSuggestions] = useState<LinkTarget[]>([]);
  const [showLinkSuggestions, setShowLinkSuggestions] = useState(false);

  // Fetch list of notes
  const { data: notesList, isLoading: notesLoading } = useQuery({
    queryKey: ['/notes'],
    queryFn: () => request('/api/notes?limit=100', { method: 'GET' }),
  });

  // Fetch selected note
  const { data: selectedNote, isLoading: noteLoading } = useQuery(
    {
      queryKey: [`/notes/${selectedNoteId}`],
      queryFn: () => request(`/api/notes/${selectedNoteId}`, { method: 'GET' }),
    },
    { enabled: !!selectedNoteId }
  );

  // Fetch graph
  const { data: graph } = useQuery({
    queryKey: ['/notes/graph'],
    queryFn: () => request('/api/notes/graph', { method: 'GET' }),
  });

  // Fetch backlinks for selected note
  const { data: backlinks } = useQuery(
    {
      queryKey: [`/notes/${selectedNoteId}/backlinks`],
      queryFn: () => request(`/api/notes/${selectedNoteId}/backlinks`, { method: 'GET' }),
    },
    { enabled: !!selectedNoteId && viewMode === 'backlinks' }
  );

  // Update note mutation
  const updateNoteMutation = useMutation({
    mutationFn: (data: { title: string; body: string }) =>
      request(`/api/notes/${selectedNoteId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      // Invalidate and refetch
    },
  });

  // Create note mutation
  const createNoteMutation = useMutation({
    mutationFn: (data: { title: string; body: string }) =>
      request('/api/notes', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (data) => {
      setSelectedNoteId(data.id);
      setEditingTitle(data.title);
      setEditingBody(data.body);
    },
  });

  // Load note content when selected
  useEffect(() => {
    if (selectedNote) {
      setEditingTitle(selectedNote.title);
      setEditingBody(selectedNote.body);
    }
  }, [selectedNote]);

  // Handle wikilink autocomplete
  const handleBodyChange = (text: string) => {
    setEditingBody(text);

    // Detect wikilink in progress
    const lastBracket = text.lastIndexOf('[[');
    const lastCloseBracket = text.lastIndexOf(']]');

    if (lastBracket !== -1 && (lastCloseBracket === -1 || lastBracket > lastCloseBracket)) {
      const query = text.substring(lastBracket + 2).split('|')[0];
      if (query.length > 0) {
        // Fetch suggestions
        request(`/api/notes/link-targets?q=${encodeURIComponent(query)}`)
          .then(setLinkSuggestions)
          .catch(() => setLinkSuggestions([]));
        setShowLinkSuggestions(true);
      }
    } else {
      setShowLinkSuggestions(false);
    }
  };

  const handleSave = () => {
    if (!selectedNoteId) {
      createNoteMutation.mutate({
        title: editingTitle || 'Untitled',
        body: editingBody,
      });
    } else {
      updateNoteMutation.mutate({
        title: editingTitle,
        body: editingBody,
      });
    }
  };

  const handleNewNote = () => {
    setSelectedNoteId(null);
    setEditingTitle('');
    setEditingBody('');
  };

  return (
    <div className="notes-editor">
      {/* Left sidebar: notes list */}
      <div className="notes-sidebar">
        <div className="notes-header">
          <h2>Notes</h2>
          <button onClick={handleNewNote} className="btn-new">+ New</button>
        </div>
        <div className="notes-list">
          {notesLoading ? (
            <p>Loading notes...</p>
          ) : (
            notesList?.notes?.map((note: Note) => (
              <div
                key={note.id}
                className={`note-item ${selectedNoteId === note.id ? 'active' : ''}`}
                onClick={() => setSelectedNoteId(note.id)}
              >
                <div className="note-title">{note.title}</div>
                <div className="note-date">{new Date(note.updated_at || note.created_at || '').toLocaleDateString()}</div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main area */}
      <div className="notes-main">
        {/* Mode tabs */}
        <div className="notes-tabs">
          <button
            className={`tab ${viewMode === 'editor' ? 'active' : ''}`}
            onClick={() => setViewMode('editor')}
          >
            Editor
          </button>
          <button
            className={`tab ${viewMode === 'graph' ? 'active' : ''}`}
            onClick={() => setViewMode('graph')}
          >
            Graph
          </button>
          {selectedNoteId && (
            <button
              className={`tab ${viewMode === 'backlinks' ? 'active' : ''}`}
              onClick={() => setViewMode('backlinks')}
            >
              Backlinks
            </button>
          )}
        </div>

        {/* Editor view */}
        {viewMode === 'editor' && (
          <div className="editor-view">
            {selectedNoteId ? (
              <>
                <input
                  type="text"
                  className="note-title-input"
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  placeholder="Note title"
                />
                <div className="editor-hint">Tip: Use [[product:name]] or [[note:name]] to link</div>
                <textarea
                  className="note-body-input"
                  value={editingBody}
                  onChange={(e) => handleBodyChange(e.target.value)}
                  placeholder="Start typing... Use [[ to link to products or notes"
                />
                {showLinkSuggestions && linkSuggestions.length > 0 && (
                  <div className="link-suggestions">
                    {linkSuggestions.map((target) => (
                      <div key={`${target.kind}:${target.ref}`} className="suggestion-item">
                        <span className="suggestion-kind">{target.kind}</span>
                        <span className="suggestion-title">{target.title}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="editor-footer">
                  <button onClick={handleSave} className="btn-save" disabled={updateNoteMutation.isPending}>
                    {updateNoteMutation.isPending ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p>No note selected</p>
                <button onClick={handleNewNote} className="btn-primary">Create a new note</button>
              </div>
            )}
          </div>
        )}

        {/* Graph view */}
        {viewMode === 'graph' && (
          <div className="graph-view">
            <div className="graph-info">
              <p>{graph?.nodes?.length || 0} nodes, {graph?.edges?.length || 0} edges</p>
            </div>
            <svg className="graph-svg">
              {/* Simple force-directed graph rendering */}
              {graph?.edges?.map((edge, idx) => (
                <line
                  key={`edge-${idx}`}
                  x1={`${(idx % 10) * 60 + 50}`}
                  y1="50"
                  x2={`${((idx + 1) % 10) * 60 + 50}`}
                  y2="150"
                  stroke="#ccc"
                  strokeWidth="1"
                />
              ))}
              {graph?.nodes?.map((node, idx) => (
                <g key={`node-${idx}`}>
                  <circle
                    cx={`${(idx % 10) * 60 + 50}`}
                    cy={idx < 10 ? '50' : '150'}
                    r="20"
                    fill={node.kind === 'note' ? '#3b82f6' : '#ec4899'}
                    opacity="0.8"
                  />
                  <text
                    x={`${(idx % 10) * 60 + 50}`}
                    y={idx < 10 ? '55' : '155'}
                    textAnchor="middle"
                    fontSize="11"
                    fill="white"
                  >
                    {node.title.substring(0, 8)}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        )}

        {/* Backlinks view */}
        {viewMode === 'backlinks' && (
          <div className="backlinks-view">
            {backlinks && backlinks.length > 0 ? (
              <div className="backlinks-list">
                <h3>Notes linking here</h3>
                {backlinks.map((note: Note) => (
                  <div
                    key={note.id}
                    className="backlink-item"
                    onClick={() => setSelectedNoteId(note.id)}
                  >
                    <div className="backlink-title">{note.title}</div>
                    <div className="backlink-preview">{note.body.substring(0, 100)}...</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">No notes link to this one</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default NotesEditor;
