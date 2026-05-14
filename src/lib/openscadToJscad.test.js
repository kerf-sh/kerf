import { describe, it, expect } from 'vitest'
import { openscadToJscad } from './openscadToJscad.js'

describe('openscadToJscad', () => {
  it('1. cube with size array', () => {
    const out = openscadToJscad('cube([10, 20, 30]);')
    expect(out).toContain('cube({size: [10, 20, 30]})')
  })

  it('2. cube with scalar', () => {
    const out = openscadToJscad('cube(5);')
    expect(out).toContain('cube({size: 5})')
  })

  it('3. sphere with r= param', () => {
    const out = openscadToJscad('sphere(r=7);')
    expect(out).toContain('sphere({radius: 7})')
  })

  it('4. sphere with positional param', () => {
    const out = openscadToJscad('sphere(3);')
    expect(out).toContain('sphere({radius: 3})')
  })

  it('5. cylinder with r and h params', () => {
    const out = openscadToJscad('cylinder(r=5, h=20);')
    expect(out).toContain('cylinder({radius: 5, height: 20})')
  })

  it('6. translate wrapping a cube', () => {
    const out = openscadToJscad('translate([1, 2, 3]) { cube([5, 5, 5]); }')
    expect(out).toContain('translate([1, 2, 3]')
    expect(out).toContain('cube({size: [5, 5, 5]})')
  })

  it('7. rotate wrapping a sphere (degrees to radians)', () => {
    const out = openscadToJscad('rotate([90, 0, 0]) { sphere(r=4); }')
    // 90 degrees = PI/2 radians ≈ 1.570796
    expect(out).toContain('rotate(')
    expect(out).toContain('sphere({radius: 4})')
    // Should have converted 90 degrees to radians
    expect(out).toMatch(/1\.5707/)
  })

  it('8. scale wrapping a cube', () => {
    const out = openscadToJscad('scale([2, 2, 2]) { cube(1); }')
    expect(out).toContain('scale([2, 2, 2]')
    expect(out).toContain('cube({size: 1})')
  })

  it('9. union of two cubes', () => {
    const out = openscadToJscad('union() { cube([1,1,1]); sphere(r=1); }')
    expect(out).toContain('union(')
    expect(out).toContain('cube({size: [1, 1, 1]})')
    expect(out).toContain('sphere({radius: 1})')
  })

  it('10. difference of two shapes', () => {
    const out = openscadToJscad('difference() { cube([5,5,5]); sphere(r=3); }')
    expect(out).toContain('subtract(')
    expect(out).toContain('cube({size: [5, 5, 5]})')
    expect(out).toContain('sphere({radius: 3})')
  })

  it('11. intersection of two shapes', () => {
    const out = openscadToJscad('intersection() { cube([5,5,5]); sphere(r=4); }')
    expect(out).toContain('intersect(')
    expect(out).toContain('cube({size: [5, 5, 5]})')
    expect(out).toContain('sphere({radius: 4})')
  })

  it('12. variable assignment', () => {
    const out = openscadToJscad('x = 42;')
    expect(out).toContain('const x = 42')
  })

  it('13. nested: translate containing difference of cube and sphere', () => {
    const src = `
      translate([0, 0, 5]) {
        difference() {
          cube([10, 10, 10]);
          sphere(r=6);
        }
      }
    `
    const out = openscadToJscad(src)
    expect(out).toContain('translate(')
    expect(out).toContain('subtract(')
    expect(out).toContain('cube({size: [10, 10, 10]})')
    expect(out).toContain('sphere({radius: 6})')
  })

  it('14. module definition', () => {
    const src = `
      module box(w=10, h=5) {
        cube([w, h, h]);
      }
    `
    const out = openscadToJscad(src)
    expect(out).toContain('function box(')
    expect(out).toContain('w = 10')
    expect(out).toContain('h = 5')
  })

  it('15. function definition', () => {
    const src = 'function double(x) = x * 2;'
    const out = openscadToJscad(src)
    expect(out).toContain('const double = (x) =>')
    expect(out).toContain('x * 2')
  })

  it('16. emits JSCAD header with imports', () => {
    const out = openscadToJscad('cube(1);')
    expect(out).toContain("import { primitives, transforms, booleans } from '@jscad/modeling'")
    expect(out).toContain('const { cube, sphere, cylinder } = primitives')
    expect(out).toContain('const { translate, rotate, scale } = transforms')
    expect(out).toContain('const { union, subtract, intersect } = booleans')
  })

  it('17. emits main() export', () => {
    const out = openscadToJscad('cube(1);')
    expect(out).toContain('export function main()')
  })

  it('18. string variable assignment', () => {
    const out = openscadToJscad('name = "widget";')
    expect(out).toContain('const name = "widget"')
  })
})
