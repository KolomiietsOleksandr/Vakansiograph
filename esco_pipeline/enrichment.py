from esco_pipeline.esco_interface import ESCOIndexInterface


class GraphEnrichment:
    """Expands candidate URIs via ESCO hierarchy (parents and siblings)."""

    def __init__(self, esco_index: ESCOIndexInterface, sibling_threshold: float = 0.5):
        self._index = esco_index
        self._sibling_threshold = sibling_threshold

    def enrich(
        self,
        candidate_uris: list[str],
        skill_texts_by_uri: dict[str, list[str]] | None = None,
        uri_scores: dict[str, float] | None = None,
    ) -> tuple[list[str], dict[str, str], dict[str, float]]:
        """Expand candidate URIs via ESCO hierarchy.

        Returns:
            (expanded_uris, graph_uri_categories, scores)
            - expanded_uris: all URIs (originals + graph-discovered)
            - graph_uri_categories: mapping of graph URI -> "graph_parent" or "graph_sibling"
            - scores: mapping of URI -> score (includes input scores + graph scores)
        """
        original_set: set[str] = set(candidate_uris)
        expanded: list[str] = list(candidate_uris)
        seen: set[str] = set(candidate_uris)
        scores: dict[str, float] = dict(uri_scores) if uri_scores else {}
        graph_uri_categories: dict[str, str] = {}

        for uri in candidate_uris:
            parent = self._index.get_parent(uri)
            if parent and parent.uri not in seen:
                expanded.append(parent.uri)
                seen.add(parent.uri)
                graph_uri_categories[parent.uri] = "graph_parent"
                child_score = scores.get(uri, 0.5)
                scores[parent.uri] = child_score

            # Get skill texts that produced this URI for similarity filtering
            source_texts = (skill_texts_by_uri or {}).get(uri, [])

            for sibling in self._index.get_siblings(uri):
                if sibling.uri in seen:
                    continue

                # Filter siblings by embedding similarity if we have source texts
                if source_texts and self._sibling_threshold > 0:
                    max_sim = max(
                        self._index.compute_embedding_similarity(text, sibling.uri)
                        for text in source_texts
                    )
                    if max_sim < self._sibling_threshold:
                        continue
                    # Use the computed similarity as the sibling score
                    scores[sibling.uri] = max_sim
                else:
                    # No source texts or threshold disabled — use a modest default
                    scores.setdefault(sibling.uri, 0.4)

                expanded.append(sibling.uri)
                seen.add(sibling.uri)
                graph_uri_categories[sibling.uri] = "graph_sibling"

        return expanded, graph_uri_categories, scores
