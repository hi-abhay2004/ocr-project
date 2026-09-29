import { describe, expect, it } from 'vitest'
import { parseCsv } from '@/components/CsvImportDialog'

describe('parseCsv', () => {
  it('reads a file with a header row', () => {
    const rows = parseCsv('USN,Name,Email\n1BY22CS001,Charan,charan@bmsit.in')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ usn: '1BY22CS001', name: 'Charan', email: 'charan@bmsit.in' })
    expect(rows[0].error).toBeUndefined()
  })

  it('falls back to positional columns when there is no header', () => {
    const rows = parseCsv('1BY22CS001,Charan,charan@bmsit.in')
    expect(rows).toHaveLength(1)
    expect(rows[0].usn).toBe('1BY22CS001')
  })

  it('accepts common header aliases', () => {
    const rows = parseCsv('Reg No,Student Name,Email ID\n1BY22CS001,Charan,c@bmsit.in')
    expect(rows[0]).toMatchObject({ usn: '1BY22CS001', name: 'Charan' })
  })

  it('handles quoted fields containing commas', () => {
    // Excel emits these the moment a name has a comma in it.
    const rows = parseCsv('usn,name,email\n1BY22CS001,"Reddy, Kesav",k@bmsit.in')
    expect(rows[0].name).toBe('Reddy, Kesav')
  })

  it('flags a duplicate USN inside the same file', () => {
    const rows = parseCsv('usn,name,email\n1BY22CS001,A,a@x.in\n1BY22CS001,B,b@x.in')
    expect(rows[0].error).toBeUndefined()
    expect(rows[1].error).toMatch(/duplicate/i)
  })

  it('flags malformed USNs, missing names and bad emails', () => {
    const rows = parseCsv('usn,name,email\n!!,A,a@x.in\n1BY22CS002,,b@x.in\n1BY22CS003,C,not-an-email')
    expect(rows[0].error).toMatch(/malformed/i)
    expect(rows[1].error).toMatch(/name is missing/i)
    expect(rows[2].error).toMatch(/email/i)
  })

  it('ignores blank trailing lines', () => {
    const rows = parseCsv('usn,name,email\n1BY22CS001,A,a@x.in\n\n\n')
    expect(rows).toHaveLength(1)
  })
})
