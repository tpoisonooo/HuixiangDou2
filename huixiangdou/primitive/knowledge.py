import uuid
import itertools
import json
import logging
import re
import networkx as nx
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

# Modified from db-gpt
class Direction(Enum):
    """Direction class."""
    OUT = 0
    IN = 1
    BOTH = 2

class Elem(ABC):
    """Elem class."""

    def __init__(self, name: Optional[str] = None):
        """Initialize Elem."""
        self._name = name
        self._props: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        """Return the edge label."""
        return self._name or ""

    @property
    def props(self) -> Dict[str, Any]:
        """Get all the properties of Elem."""
        return self._props

    def set_prop(self, key: str, value: Any):
        """Set a property of ELem."""
        self._props[key] = value

    def get_prop(self, key: str):
        """Get one of the properties of Elem."""
        return self._props.get(key)

    def del_prop(self, key: str):
        """Delete a property of ELem."""
        self._props.pop(key, None)

    def has_props(self, **props):
        """Check all key-value pairs exist."""
        return all(self._props.get(k) == v for k, v in props.items())

    @abstractmethod
    def format(self) -> str:
        """Format properties into a string."""
        if len(self._props) == 1:
            return str(next(iter(self._props.values())))

        formatted_props = [
            f"{k}:{json.dumps(v, ensure_ascii=False)}" for k, v in self._props.items()
        ]
        return f"{{{';'.join(formatted_props)}}}"

class Vertex(Elem):
    """Vertex class."""

    def __init__(self, vid: str, name: Optional[str] = None, **props):
        """Initialize Vertex."""
        super().__init__(name)
        self._vid = vid
        if len(vid) > 64:
            import pdb
            pdb.set_trace()
            pass
            
        for k, v in props.items():
            self.set_prop(k, v)

    @property
    def vid(self) -> str:
        """Return the vertex ID."""
        return self._vid

    @property
    def name(self) -> str:
        """Return the vertex name."""
        return super().name or self._vid

    def format(self, concise: bool = False):
        """Format vertex into a string."""
        name = self._name or self._vid
        if concise:
            return f"({name})"

        if self._props:
            return f"({name}:{super().format()})"
        else:
            return f"({name})"

    def __str__(self):
        """Return the vertex ID as its string representation."""
        return f"({self._vid})"

    def __repr__(self):
        return self.__str__()
        
class IdVertex(Vertex):
    """IdVertex class."""

    def __init__(self, vid: str):
        """Initialize Idvertex."""
        super().__init__(vid)

class Edge(Elem):
    """Edge class."""

    def __init__(self, sid: str, tid: str, name: str, **props):
        """Initialize Edge."""
        if name is None or len(name) < 1:
            import pdb
            pdb.set_trace()
            assert name, "Edge name is required"

        super().__init__(name)
        self._sid = sid
        self._tid = tid
        for k, v in props.items():
            self.set_prop(k, v)

    @property
    def sid(self) -> str:
        """Return the source vertex ID of the edge."""
        return self._sid

    @property
    def tid(self) -> str:
        """Return the target vertex ID of the edge."""
        return self._tid

    def nid(self, vid):
        """Return neighbor id."""
        if vid == self._sid:
            return self._tid
        elif vid == self._tid:
            return self._sid
        else:
            raise ValueError(f"Get nid of {vid} on {self} failed")

    def format(self):
        """Format the edge properties into a string."""
        if self._props:
            return f"-[{self._name}:{super().format()}]->"
        else:
            return f"-[{self._name}]->"

    def triplet(self) -> Tuple[str, str, str]:
        """Return a triplet."""
        return self.sid, self.name, self.tid

    def __str__(self):
        """Return the edge '(sid)->(tid)'."""
        return f"({self._sid})-[{self._name}]->({self._tid})"
    
    def __repr__(self):
        return self.__str__()

class Graph(ABC):
    """Graph class."""

    @abstractmethod
    def upsert_vertex(self, vertex: Vertex):
        """Add a vertex."""

    @abstractmethod
    def append_edge(self, edge: Edge):
        """Add an edge."""

    @abstractmethod
    def has_vertex(self, vid: str) -> bool:
        """Check vertex exists."""

    @abstractmethod
    def get_vertex(self, vid: str) -> Vertex:
        """Get a vertex."""

    @abstractmethod
    def vertices(self) -> Iterator[Vertex]:
        """Get vertex iterator."""

    @abstractmethod
    def edges(self) -> Iterator[Edge]:
        """Get edge iterator."""

    @abstractmethod
    def del_vertices(self, *vids: str):
        """Delete vertices and their neighbor edges."""

    @abstractmethod
    def del_edges(self, sid: str, tid: str, name: str, **props):
        """Delete edges(sid -[name]-> tid) matches props."""

    @abstractmethod
    def del_neighbor_edges(self, vid: str, direction: Direction = Direction.OUT):
        """Delete neighbor edges."""

    @abstractmethod
    def search(
        self,
        vids: List[str],
        direct: Direction = Direction.OUT,
        depth: Optional[int] = None,
        fan: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> "Graph":
        """Search on graph."""

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """Get schema."""

    @abstractmethod
    def format(self) -> str:
        """Format graph data to string."""

    @abstractmethod
    def truncate(self):
        """Truncate graph."""

    @abstractmethod
    async def get_neighbor_edges(
        self,
        vid: str,
        direction: Direction = Direction.OUT,
        limit: Optional[int] = None,
    ) -> Iterator[Edge]:
        """Get neighbor edges."""

class MemoryGraph(Graph):
    """MemoryGraph class."""

    def __init__(self):
        """Initialize MemoryGraph with vertex label and edge label."""
        # metadata
        self._vertex_prop_keys = set()
        self._edge_prop_keys = set()
        self._edge_count = 0

        # init vertices, out edges, in edges index
        self._vs: Any = defaultdict()
        self._oes: Any = defaultdict(lambda: defaultdict(set))
        self._ies: Any = defaultdict(lambda: defaultdict(set))

    @property
    def vertex_count(self):
        """Return the number of vertices in the graph."""
        return len(self._vs)

    @property
    def edge_count(self):
        """Return the count of edges in the graph."""
        return self._edge_count

    def upsert_vertex(self, vertex: Vertex):
        """Insert or update a vertex based on its ID."""
        if vertex.vid in self._vs:
            if isinstance(self._vs[vertex.vid], IdVertex):
                self._vs[vertex.vid] = vertex
            else:
                self._vs[vertex.vid].props.update(vertex.props)
        else:
            self._vs[vertex.vid] = vertex

        # update metadata
        self._vertex_prop_keys.update(vertex.props.keys())
        
    def upsert_node(self, name:str, data:dict):
        if name is None:
            import pdb
            pdb.set_trace()
        v = Vertex(vid=name, name=name, **data)
        return self.upsert_vertex(v)

    def has_edge(self, sid:str, tid:str) -> bool:
        if sid not in self._oes:
            return False
        if tid not in self._oes[sid]:
            return False
        return True
    
    def get_edge(self, sid: str, tid: str) -> Optional[Edge]:
        """
        Retrieve an edge by source vertex ID, target vertex ID, and edge name.

        Args:
        sid (str): The source vertex ID.
        tid (str): The target vertex ID.
        name (str): The edge name.

        Returns:
        Optional[Edge]: The edge if found, otherwise None.
        """
        # Check if the source vertex exists in the outgoing edges dictionary
        if sid in self._oes:
            # Check if the target vertex exists in the outgoing edges from the source vertex
            if tid in self._oes[sid]:
                # Iterate over the edges from source to target
                return self._oes[sid][tid]
        # Return None if no edge is found
        return None

    def append_edge(self, edge: Edge):
        """Append an edge if it doesn't exist; requires edge label."""
        sid = edge.sid
        tid = edge.tid

        if edge in self._oes[sid][tid]:
            return False

        # init vertex index
        self._vs.setdefault(sid, IdVertex(sid))
        self._vs.setdefault(tid, IdVertex(tid))

        # update edge index
        self._oes[sid][tid].add(edge)
        self._ies[tid][sid].add(edge)

        # update metadata
        self._edge_prop_keys.update(edge.props.keys())
        self._edge_count += 1
        return True

    def upsert_edge(self, sid:str, tid:str, name:str, data:dict):
        """
        Insert or update an edge based on its source and target vertex IDs.
        If the edge already exists, update its properties. Otherwise, insert the edge.

        Args:
        edge (Edge): The edge to be inserted or updated.

        Returns:
        bool: True if the edge is inserted or updated successfully, False otherwise.
        """
        edge = Edge(sid, tid, name, **data)

        # Check if the edge already exists
        existing_edges = self._oes[sid].get(tid, set())
        for existing_edge in existing_edges:
            if existing_edge.name == edge.name and existing_edge.has_props(**edge.props):
                # Update the existing edge's properties
                existing_edge.props.update(edge.props)
                return True

        # If the edge does not exist, insert it
        self.append_edge(edge)
        return False
    
    def has_vertex(self, vid: str) -> bool:
        """Retrieve a vertex by ID."""
        return vid in self._vs
    
    def get_vertex(self, vid: str) -> Vertex:
        """Retrieve a vertex by ID."""
        if vid not in self._vs:
            return None
        return self._vs[vid]
    
    def has_node(self, vid: str) -> bool:
        return self.has_vertex(vid=vid)
    
    def get_node(self, vid:str) -> Vertex:
        return self.get_vertex(vid)

    def vertices(self) -> Iterator[Vertex]:
        """Return vertices."""
        return iter(self._vs.values())

    def edges(self) -> Iterator[Edge]:
        """Return edges."""
        return iter(e for nbs in self._oes.values() for es in nbs.values() for e in es)
    
    async def node_degree(self, vid:str) -> int:
        ret = 0
        if vid in self._oes:
            ret += len(self._oes[vid])
        if vid in self._ies:
            ret += len(self._ies[vid])
        return ret

    def del_vertices(self, *vids: str):
        """Delete specified vertices."""
        for vid in vids:
            self.del_neighbor_edges(vid, Direction.BOTH)
            self._vs.pop(vid, None)
    
    def del_edges(self, sid: str, tid: str, name: str, **props):
        """Delete edges."""
        old_edge_cnt = len(self._oes[sid][tid])

        def remove_matches(es):
            return set(
                filter(
                    lambda e: not (
                        (name == e.name if name else True) and e.has_props(**props)
                    ),
                    es,
                )
            )

        self._oes[sid][tid] = remove_matches(self._oes[sid][tid])
        self._ies[tid][sid] = remove_matches(self._ies[tid][sid])
        self._edge_count -= old_edge_cnt - len(self._oes[sid][tid])

    def del_neighbor_edges(self, vid: str, direction: Direction = Direction.OUT):
        """Delete all neighbor edges."""

        def del_index(idx, i_idx):
            for nid in idx[vid].keys():
                self._edge_count -= len(i_idx[nid][vid])
                i_idx[nid].pop(vid, None)
            idx.pop(vid, None)

        if direction in [Direction.OUT, Direction.BOTH]:
            del_index(self._oes, self._ies)

        if direction in [Direction.IN, Direction.BOTH]:
            del_index(self._ies, self._oes)

    def schema(self) -> Dict[str, Any]:
        """Return schema."""
        return {
            "schema": [
                {
                    "type": "VERTEX",
                    "properties": [{"name": k} for k in self._vertex_prop_keys],
                },
                {
                    "type": "EDGE",
                    "properties": [{"name": k} for k in self._edge_prop_keys],
                },
            ]
        }

    def format(self) -> str:
        """Format graph to string."""
        vs_str = "\n".join(v.format() for v in self.vertices())
        es_str = "\n".join(
            f"{self.get_vertex(e.sid).format(concise=True)}"
            f"{e.format()}"
            f"{self.get_vertex(e.tid).format(concise=True)}"
            for e in self.edges()
        )
        return (
            f"Entities:\n{vs_str}\n\n" f"Relationships:\n{es_str}"
            if (vs_str or es_str)
            else ""
        )

    def truncate(self):
        """Truncate graph."""
        # clean metadata
        self._vertex_prop_keys.clear()
        self._edge_prop_keys.clear()
        self._edge_count = 0

        # clean data and index
        self._vs.clear()
        self._oes.clear()
        self._ies.clear()

    def graphviz(self, name="g"):
        """View graphviz graph: https://dreampuf.github.io/GraphvizOnline."""
        g = nx.MultiDiGraph()
        for vertex in self.vertices():
            g.add_node(vertex.vid)

        for edge in self.edges():
            triplet = edge.triplet()
            g.add_edge(triplet[0], triplet[2], label=triplet[1])

        digraph = nx.nx_agraph.to_agraph(g).to_string()
        digraph = digraph.replace('digraph ""', f"digraph {name}")
        digraph = re.sub(r"key=\d+,?\s*", "", digraph)
        return digraph

    async def search(
        self,
        vids: List[str],
        direct: Direction = Direction.OUT,
        depth: Optional[int] = None,
        fan: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> "MemoryGraph":
        """@return: MemoryGraph"""
        subgraph = MemoryGraph()

        for vid in vids:
            await self.__search(vid, direct, depth, fan, limit, 0, set(), subgraph)

        return subgraph

    async def __search(
        self,
        vid: str,
        direct: Direction,
        depth: Optional[int],
        fan: Optional[int],
        limit: Optional[int],
        _depth: int,
        _visited: Set,
        _subgraph: "MemoryGraph",
    ):
        if vid in _visited or depth and _depth >= depth:
            return

        # visit vertex
        if not self.has_vertex(vid):
            return
        _subgraph.upsert_vertex(self.get_vertex(vid))
        _visited.add(vid)

        # visit edges
        nids = set()
        async for edge in self.get_neighbor_edges(vid, direct, fan):
            if limit and _subgraph.edge_count >= limit:
                return

            # append edge success then visit new vertex
            if _subgraph.append_edge(edge):
                nid = edge.nid(vid)
                if nid not in _visited:
                    nids.add(nid)

        # next hop
        for nid in nids:
            await self.__search(
                nid, direct, depth, fan, limit, _depth + 1, _visited, _subgraph
            )
    
    async def edge_degree(self, sid: str, tid: str) -> int:
        return await self.node_degree(vid=sid) + await self.node_degree(vid=tid)
    
    async def get_neighbor_edges(
        self,
        vid: str,
        direction: Direction = Direction.OUT,
        limit: Optional[int] = None,
    ) -> Iterator[Edge]:
        """Get edges connected to a vertex by direction."""
        if direction == Direction.OUT:
            es = (e for es in self._oes[vid].values() for e in es)

        elif direction == Direction.IN:
            es = iter(e for es in self._ies[vid].values() for e in es)

        elif direction == Direction.BOTH:
            oes = (e for es in self._oes[vid].values() for e in es)
            ies = (e for es in self._ies[vid].values() for e in es)

            # merge
            tuples = itertools.zip_longest(oes, ies)
            es = (e for t in tuples for e in t if e is not None)

            # distinct
            seen = set()

            # es = (e for e in es if e not in seen and not seen.add(e))
            def unique_elements(elements):
                for element in elements:
                    if element not in seen:
                        seen.add(element)
                        yield element

            es = unique_elements(es)
        else:
            raise ValueError(f"Invalid direction: {direction}")

        return itertools.islice(es, limit) if limit else es
