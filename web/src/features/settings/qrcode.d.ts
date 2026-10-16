declare module 'qrcode' {
  interface Opts {
    margin?: number
    width?: number
    color?: { dark?: string; light?: string }
  }
  const QR: { toDataURL(text: string, opts?: Opts): Promise<string> }
  export default QR
}
