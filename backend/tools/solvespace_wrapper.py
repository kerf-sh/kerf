import math
from dataclasses import dataclass
from typing import Any

IDENTITY_4X4 = (1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0)


@dataclass
class Entity:
    id: str
    entity_type: str
    component_id: str
    feature_id: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)


@dataclass
class MateConstraint:
    id: str
    mate_type: str
    entity_a_id: str
    entity_b_id: str
    value: float = 0.0
    unit: str = "mm"
    tolerance_plus: float = 0.0
    tolerance_minus: float = 0.0
    flipped: bool = False


@dataclass
class SolveResult:
    solved: bool
    entities: dict[str, Entity]
    residuals: list[float]
    iterations: int
    error: str = ""


def vec3_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec3_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec3_scale(v: tuple[float, float, float], s: float) -> tuple[float, float, float]:
    return (v[0] * s, v[1] * s, v[2] * s)


def vec3_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec3_cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vec3_norm(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def vec3_normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = vec3_norm(v)
    if n < 1e-10:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def vec3_angle(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    a_n = vec3_normalize(a)
    b_n = vec3_normalize(b)
    cos_angle = max(-1.0, min(1.0, vec3_dot(a_n, b_n)))
    return math.acos(cos_angle)


def vec3_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return vec3_norm(vec3_sub(a, b))


def transform_point(p: tuple[float, float, float], m: tuple[float, ...]) -> tuple[float, float, float]:
    x = m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3]
    y = m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7]
    z = m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11]
    w = m[12] * p[0] + m[13] * p[1] + m[14] * p[2] + m[15]
    if abs(w) > 1e-10:
        return (x / w, y / w, z / w)
    return (x, y, z)


def transform_normal(n: tuple[float, float, float], m: tuple[float, ...]) -> tuple[float, float, float]:
    x = m[0] * n[0] + m[1] * n[1] + m[2] * n[2]
    y = m[4] * n[0] + m[5] * n[1] + m[6] * n[2]
    z = m[8] * n[0] + m[9] * n[1] + m[10] * n[2]
    return vec3_normalize((x, y, z))


def extract_transform(component: dict[str, Any]) -> tuple[float, ...]:
    t = component.get("transform", IDENTITY_4X4)
    if len(t) == 16:
        return tuple(t)
    return IDENTITY_4X4


def apply_transform_to_entity(entity: Entity, transform: tuple[float, ...]) -> Entity:
    new_pos = transform_point(entity.position, transform)
    new_normal = transform_normal(entity.normal, transform)
    new_axis = transform_normal(entity.axis, transform)
    return Entity(
        id=entity.id,
        entity_type=entity.entity_type,
        component_id=entity.component_id,
        feature_id=entity.feature_id,
        position=new_pos,
        normal=new_normal,
        axis=new_axis,
    )


class GeometricConstraintSolver:
    def __init__(self, entities: list[Entity], constraints: list[MateConstraint]):
        self.entities = {e.id: e for e in entities}
        self.constraints = constraints
        self.max_iterations = 100
        self.tolerance = 1e-6

    def _get_entity(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    def _constraint_residual(self, c: MateConstraint) -> float:
        e_a = self._get_entity(c.entity_a_id)
        e_b = self._get_entity(c.entity_b_id)
        if e_a is None or e_b is None:
            return 0.0

        if c.mate_type == "coincident":
            return vec3_distance(e_a.position, e_b.position)

        elif c.mate_type == "distance":
            if c.flipped:
                e_a, e_b = e_b, e_a
            dist = vec3_distance(e_a.position, e_b.position)
            target = self._to_mm(c.value, c.unit)
            return dist - target

        elif c.mate_type == "angle":
            if c.flipped:
                e_a, e_b = e_b, e_a
            angle = vec3_angle(e_a.normal, e_b.normal)
            target = self._to_radians(c.value, c.unit)
            return angle - target

        elif c.mate_type == "parallel":
            angle = vec3_angle(e_a.normal, e_b.normal)
            return min(angle, math.pi - angle)

        elif c.mate_type == "perpendicular":
            angle = vec3_angle(e_a.normal, e_b.normal)
            return abs(angle - math.pi / 2)

        elif c.mate_type == "concentric":
            dist = vec3_distance(e_a.position, e_b.position)
            return dist

        elif c.mate_type == "tangent":
            dist = vec3_distance(e_a.position, e_b.position)
            return dist

        return 0.0

    def _to_mm(self, value: float, unit: str) -> float:
        if unit == "inch":
            return value * 25.4
        elif unit == "cm":
            return value * 10.0
        return value

    def _to_radians(self, value: float, unit: str) -> float:
        if unit in ("deg", "degree", "degrees"):
            return math.radians(value)
        return value

    def _compute_gradient(self, c: MateConstraint, entity_id: str) -> tuple[float, float, float]:
        e = self._get_entity(entity_id)
        if e is None:
            return (0.0, 0.0, 0.0)

        eps = 1e-7
        residuals = []
        for i in range(3):
            pos = list(e.position)
            pos[i] += eps
            old_pos = e.position
            e.position = tuple(pos)
            r_plus = self._constraint_residual(c)
            pos[i] -= 2 * eps
            e.position = tuple(pos)
            r_minus = self._constraint_residual(c)
            e.position = old_pos
            residuals.append((r_plus - r_minus) / (2 * eps))

        return tuple(residuals)

    def solve(self) -> SolveResult:
        entity_ids = list(self.entities.keys())
        positions = {eid: list(self.entities[eid].position) for eid in entity_ids}

        for iteration in range(self.max_iterations):
            residuals = []
            for c in self.constraints:
                r = self._constraint_residual(c)
                residuals.append(r)

            max_residual = max(abs(r) for r in residuals) if residuals else 0.0
            if max_residual < self.tolerance:
                return SolveResult(
                    solved=True,
                    entities=self.entities,
                    residuals=residuals,
                    iterations=iteration + 1,
                )

            for eid in entity_ids:
                grad = [0.0, 0.0, 0.0]
                for c in self.constraints:
                    if c.entity_a_id == eid or c.entity_b_id == eid:
                        g = self._compute_gradient(c, eid)
                        r = self._constraint_residual(c)
                        for i in range(3):
                            grad[i] += r * g[i]

                step_size = 0.1
                for i in range(3):
                    positions[eid][i] -= step_size * grad[i]

                entity = self.entities[eid]
                self.entities[eid] = Entity(
                    id=entity.id,
                    entity_type=entity.entity_type,
                    component_id=entity.component_id,
                    feature_id=entity.feature_id,
                    position=tuple(positions[eid]),
                    normal=entity.normal,
                    axis=entity.axis,
                )

        final_residuals = [self._constraint_residual(c) for c in self.constraints]
        return SolveResult(
            solved=False,
            entities=self.entities,
            residuals=final_residuals,
            iterations=self.max_iterations,
            error="Failed to converge",
        )


def compute_tolerance_stackup(
    constraints: list[MateConstraint],
    method: str = "both",
) -> dict[str, Any]:
    results = {}

    for c in constraints:
        if c.mate_type not in ("distance", "angle"):
            continue

        nominal = c.value
        plus = c.tolerance_plus
        minus = c.tolerance_minus

        worst_case_max = nominal + plus
        worst_case_min = nominal - minus

        rss_band = math.sqrt(plus ** 2 + minus ** 2)

        results[c.id] = {
            "nominal": nominal,
            "worst_case": {
                "max": worst_case_max,
                "min": worst_case_min,
                "tolerance": plus + minus,
            },
            "rss": {
                "band": rss_band,
                "max": nominal + rss_band,
                "min": nominal - rss_band,
            },
        }

    return results


def solve_assembly(
    components: list[dict[str, Any]],
    mates: list[dict[str, Any]],
    fixed_component_id: str | None = None,
) -> dict[str, Any]:
    entities: list[Entity] = []
    constraints: list[MateConstraint] = []

    face_planes = {
        "plane_xy": (0.0, 0.0, 1.0),
        "plane_yz": (1.0, 0.0, 0.0),
        "plane_xz": (0.0, 1.0, 0.0),
    }

    for comp in components:
        comp_id = comp["id"]
        transform = extract_transform(comp)

        for mate in mates:
            for ref_id, ref_key in [("a", "a"), ("b", "b")]:
                ref = mate.get(ref_key, {})
                if ref.get("component_id") != comp_id:
                    continue

                feature = ref.get("feature", "face")
                feature_id = ref.get("feature_id", "")

                entity_id = f"{comp_id}_{ref_key}_{mate['id']}"

                normal = (0.0, 0.0, 1.0)
                if feature == "face":
                    if feature_id in face_planes:
                        normal = face_planes[feature_id]
                    else:
                        normal = (0.0, 0.0, 1.0)
                elif feature == "axis":
                    normal = (0.0, 0.0, 1.0)

                entity = Entity(
                    id=entity_id,
                    entity_type=feature,
                    component_id=comp_id,
                    feature_id=feature_id,
                    position=(0.0, 0.0, 0.0),
                    normal=normal,
                    axis=normal,
                )

                transformed = apply_transform_to_entity(entity, transform)
                entities.append(transformed)

                constraint = MateConstraint(
                    id=mate["id"],
                    mate_type=mate["type"],
                    entity_a_id=f"{mate['a']['component_id']}_a_{mate['id']}",
                    entity_b_id=f"{mate['b']['component_id']}_b_{mate['id']}",
                    value=mate.get("value", 0.0),
                    unit=mate.get("unit", "mm"),
                    tolerance_plus=mate.get("tolerance_plus", 0.0),
                    tolerance_minus=mate.get("tolerance_minus", 0.0),
                    flipped=mate.get("flipped", False),
                )
                constraints.append(constraint)

    if fixed_component_id:
        for entity in entities:
            if entity.component_id == fixed_component_id:
                entity.position = (0.0, 0.0, 0.0)

    solver = GeometricConstraintSolver(entities, constraints)
    result = solver.solve()

    tolerance_results = compute_tolerance_stackup(constraints)

    component_transforms = {}
    for comp in components:
        comp_id = comp["id"]
        original_transform = extract_transform(comp)
        component_transforms[comp_id] = list(original_transform)

    return {
        "solved": result.solved,
        "iterations": result.iterations,
        "component_transforms": component_transforms,
        "tolerance_stackup": tolerance_results,
        "residuals": result.residuals,
        "error": result.error,
    }
