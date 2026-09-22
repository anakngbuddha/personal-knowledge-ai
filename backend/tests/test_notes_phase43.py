"""Tests for Phase 4.3 notes endpoints: graph, wikilinks, backlinks."""

import pytest
from sqlalchemy.orm import Session

from app.catalog.models import slugify
from app.db.models import Note, NoteLink, NoteLinkKind, Product
from app.notes.service import create_note, update_note, sync_links
from app.notes.wikilinks import extract_wikilinks, parse_wikilink_inner


class TestWikilinks:
    def test_parse_wikilink_product(self):
        parsed = parse_wikilink_inner("product:firewall-plus")
        assert parsed.kind == NoteLinkKind.PRODUCT
        assert parsed.target_ref == "firewall-plus"
        assert parsed.prefixed

    def test_parse_wikilink_note(self):
        parsed = parse_wikilink_inner("note:meeting-notes")
        assert parsed.kind == NoteLinkKind.NOTE
        assert parsed.target_ref == "meeting-notes"

    def test_parse_wikilink_with_alias(self):
        parsed = parse_wikilink_inner("product:zoom-rooms|Zoom Rooms")
        assert parsed.kind == NoteLinkKind.PRODUCT
        assert parsed.target_ref == "zoom-rooms"
        assert parsed.display_text == "Zoom Rooms"

    def test_parse_wikilink_unprefixed(self):
        parsed = parse_wikilink_inner("firewall-plus")
        assert parsed.kind == NoteLinkKind.NOTE  # defaults to note
        assert parsed.target_ref == "firewall-plus"
        assert not parsed.prefixed

    def test_extract_wikilinks(self):
        text = "Check [[product:teams]] and [[note:meeting-notes]] for details."
        links = extract_wikilinks(text)
        assert len(links) == 2
        assert links[0].target_ref == "teams"
        assert links[1].target_ref == "meeting-notes"

    def test_extract_wikilinks_unique(self):
        text = "[[product:teams]] and [[product:teams]] again"
        links = extract_wikilinks(text)
        assert len(links) == 1  # only one unique link


class TestNoteLinks(object):
    def test_create_note_with_wikilinks(
        self, db: Session, org_uuid, workspace_uuid, user_uuid
    ):
        # Create a product to link to
        product = Product(
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            name="Teams Rooms",
            slug="teams-rooms",
            description="Microsoft Teams meeting rooms",
        )
        db.add(product)
        db.flush()

        # Create a note with a wikilink
        note_body = "This recommendation uses [[product:teams-rooms]] for huddle rooms."
        note = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Recommendation for Acme",
            body=note_body,
            created_by=user_uuid,
        )

        assert note.title == "Recommendation for Acme"
        assert len(note.links) == 1
        assert note.links[0].target_kind == NoteLinkKind.PRODUCT
        assert note.links[0].target_ref == "teams-rooms"
        assert note.links[0].resolved
        assert note.links[0].resolved_id == product.id

    def test_sync_links_updates_on_edit(
        self, db: Session, org_uuid, workspace_uuid, user_uuid
    ):
        # Create initial note
        note = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Planning",
            body="Initial text with no links",
            created_by=user_uuid,
        )
        assert len(note.links) == 0

        # Update with wikilinks
        note.body = "Now linking to [[note:acme-project]] and [[product:poly-studio]]"
        sync_links(db, note)
        db.flush()

        assert len(note.links) == 2
        refs = {link.target_ref for link in note.links}
        assert "acme-project" in refs
        assert "poly-studio" in refs

    def test_unresolved_links_still_appear(
        self, db: Session, org_uuid, workspace_uuid, user_uuid
    ):
        # Create note with link to non-existent product
        note = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Future Recommendation",
            body="Considering [[product:mythical-product]]",
            created_by=user_uuid,
        )

        assert len(note.links) == 1
        assert not note.links[0].resolved
        assert note.links[0].resolved_id is None

    def test_account_links_are_stored(
        self, db: Session, org_uuid, workspace_uuid, user_uuid
    ):
        note = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Account Note",
            body="See also [[account:acme-corp]] for context.",
            created_by=user_uuid,
        )

        assert len(note.links) == 1
        assert note.links[0].target_kind == NoteLinkKind.ACCOUNT
        assert note.links[0].target_ref == "acme-corp"
        # Accounts are always "resolved" (ref is the ID)
        assert note.links[0].resolved


class TestNoteGraph(object):
    def test_graph_has_notes_and_products(
        self, db: Session, org_uuid, workspace_uuid, user_uuid
    ):
        # Create a product
        product = Product(
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            name="Cisco WebEx",
            slug="cisco-webex",
            description="Video conferencing",
        )
        db.add(product)
        db.flush()

        # Create two notes that cross-reference
        note1 = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Huddle Room Setup",
            body="Uses [[product:cisco-webex]]",
            created_by=user_uuid,
        )

        note2 = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Video Endpoints",
            body="See [[note:huddle-room-setup]] for details",
            created_by=user_uuid,
        )

        db.commit()

        # Verify the graph has nodes and edges
        # (In real usage, this would be tested via the API endpoint)
        # For now, verify that the links were created correctly
        assert len(note1.links) == 1
        assert len(note2.links) == 1


class TestBacklinks(object):
    def test_backlinks_resolve(self, db: Session, org_uuid, workspace_uuid, user_uuid):
        """Test that backlinks_endpoint correctly returns notes linking to a target."""
        from app.notes.service import backlinks

        # Create a note
        note1 = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Core Design",
            body="Foundation for all recommendations",
            created_by=user_uuid,
        )
        db.flush()

        # Create notes that link to it
        note2 = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Acme Project",
            body="Based on [[note:core-design]]",
            created_by=user_uuid,
        )

        note3 = create_note(
            db,
            org_id=org_uuid,
            workspace_id=workspace_uuid,
            title="Beta Client",
            body="Also references [[note:core-design]] for patterns",
            created_by=user_uuid,
        )
        db.commit()

        # Query backlinks
        result = backlinks(
            db,
            org_id=org_uuid,
            kind=NoteLinkKind.NOTE,
            target_ref="core-design",
        )
        assert len(result) == 2
        titles = {n.title for n in result}
        assert "Acme Project" in titles
        assert "Beta Client" in titles


class TestSaveAnswerAsNote(object):
    def test_auto_title_generation(self):
        """Test that auto-generated titles are sensible."""
        from app.api.routes.notes import _auto_title

        # Normal markdown
        title = _auto_title("# Recommendation for Acme\nDetails here")
        assert title == "Recommendation for Acme"

        # With markdown formatting
        title = _auto_title("**Bold** and *italic* text")
        assert "Bold" in title and "italic" in title

        # Just a short paragraph
        title = _auto_title("This is a single sentence.")
        assert title == "This is a single sentence."

        # Empty or whitespace
        title = _auto_title("")
        assert title == "Untitled Note"
