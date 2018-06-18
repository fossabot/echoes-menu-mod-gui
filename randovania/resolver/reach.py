from collections import defaultdict
from typing import Dict, Set, List, Iterator, Tuple, Iterable

from randovania.resolver import debug
from randovania.resolver.game_description import calculate_interesting_resources
from randovania.resolver.node import ResourceNode, Node, is_resource_node
from randovania.resolver.requirements import RequirementList, RequirementSet, SatisfiableRequirements
from randovania.resolver.state import State


class Reach:
    _nodes: Tuple[Node]
    _satisfiable_requirements: SatisfiableRequirements

    @property
    def nodes(self) -> Iterator[Node]:
        return iter(self._nodes)

    @property
    def satisfiable_requirements(self) -> SatisfiableRequirements:
        return self._satisfiable_requirements

    @property
    def satisfiable_as_requirement_set(self) -> RequirementSet:
        return RequirementSet(self._satisfiable_requirements)

    def __init__(self, nodes: Iterable[Node], requirements: SatisfiableRequirements):
        self._nodes = tuple(nodes)
        self._satisfiable_requirements = requirements

    @classmethod
    def calculate_reach(cls,
                        initial_state: State) -> "Reach":
        logic = initial_state.logic

        checked_nodes = set()
        nodes_to_check = [initial_state.node]

        reach_nodes: List[Node] = []
        requirements_by_node: Dict[Node, Set[RequirementList]] = defaultdict(set)

        while nodes_to_check:
            node = nodes_to_check.pop()
            checked_nodes.add(node)

            if node != initial_state.node:
                reach_nodes.append(node)

            for target_node, requirements in logic.game.potential_nodes_from(node):
                if target_node in checked_nodes or target_node in nodes_to_check:
                    continue

                # Check if the normal requirements to reach that node is satisfied
                satisfied = requirements.satisfied(initial_state.resources)
                if satisfied:
                    # If it is, check if we additional requirements figured out by backtracking is satisfied
                    satisfied = logic.get_additional_requirements(node).satisfied(initial_state.resources)

                if satisfied:
                    nodes_to_check.append(target_node)
                elif target_node:
                    # If we can't go to this node, store the reason in order to build the satisfiable requirements.
                    # Note we ignore the 'additional requirements' here because it'll be added on the end.
                    requirements_by_node[target_node].update(requirements.alternatives)

        # Discard satisfiable requirements of nodes reachable by other means
        for node in set(reach_nodes).intersection(requirements_by_node.keys()):
            requirements_by_node.pop(node)

        if requirements_by_node:
            satisfiable_requirements = frozenset.union(
                *[RequirementSet(requirements).union(logic.get_additional_requirements(node)).alternatives
                  for node, requirements in requirements_by_node.items()])
        else:
            satisfiable_requirements = frozenset()

        return Reach(reach_nodes, satisfiable_requirements)

    def possible_actions(self,
                         state: State) -> Iterator[ResourceNode]:

        for node in self.uncollected_resource_nodes(state):
            if state.logic.get_additional_requirements(node).satisfied(state.resources):
                yield node
            else:
                debug.log_skip_action_missing_requirement(node, state.game)

    def satisfiable_actions(self, state: State) -> Iterator[ResourceNode]:

        if self._satisfiable_requirements:
            # print(" > interesting_resources from {} satisfiable_requirements".format(len(satisfiable_requirements)))
            interesting_resources = calculate_interesting_resources(self._satisfiable_requirements, state.resources)

            # print(" > satisfiable actions, with {} interesting resources".format(len(interesting_resources)))
            for action in self.possible_actions(state):
                for resource, amount in action.resource_gain_on_collect(state.game.resource_database,
                                                                        state.logic.patches):
                    if resource in interesting_resources:
                        yield action
                        break

    def uncollected_resource_nodes(self,
                                   state: State) -> Iterator[ResourceNode]:
        for node in self.nodes:
            if not is_resource_node(node):
                continue

            if not state.has_resource(node.resource(state.game.resource_database)):
                yield node