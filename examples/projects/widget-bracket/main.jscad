const { primitives, booleans, transforms, extrusions } = require('@jscad/modeling')
const { cuboid, cylinder, rectangle } = primitives.shapes ?? primitives
const { translate, rotateZ, mirror } = transforms
const { union, subtract } = booleans

module.exports = function ({ params }) {
  const { wall_thickness = 3, hole_diameter = 4, mount_spacing = 20 } = params || {}

  const legA = 50
  const legB = 40

  const base = cuboid({ size: [legA, wall_thickness, wall_thickness] })
  const vert = translate([0, wall_thickness, 0],
    cuboid({ size: [wall_thickness, legB, wall_thickness] }))

  const body = union(base, vert)

  const sketchCircles = [
    { x: 10, y: wall_thickness / 2 },
    { x: 10 + mount_spacing, y: wall_thickness / 2 },
    { x: 10, y: wall_thickness + 10 },
    { x: 10 + mount_spacing, y: wall_thickness + 10 }
  ]

  const holes = sketchCircles.map((c, i) =>
    translate([c.x, c.y, wall_thickness / 2],
      cylinder({ radius: hole_diameter / 2, height: wall_thickness * 2, center: true }))
  )

  const bracket = subtract(body, ...holes)

  return [
    { id: 'bracket', geom: bracket }
  ]
}
