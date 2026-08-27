# ライセンス基盤連携

このアプリは将来の販売・限定配布に備えて、専用の Supabase License Platform へ接続しています。

## 実装済み
- Supabase Authによるユーザー登録・ログイン
- ライセンスキー認証
- ライセンス開始日・有効期限
- 端末数制限
- 端末認証解除
- 7日間のオフライン利用猶予
- 更新権限期限（updates_until）
- 正規ライセンス向け最新版取得API
- 顧客コード・ライセンスID・install_idによる内部識別
- 生成PDFへの非個人ライセンス識別情報の埋め込み
- GitHub Actionsの顧客別ビルド入力

## 安全設計
- デスクトップアプリには Service Role Key を入れません。
- アプリは Supabase の publishable key とユーザーJWTだけを使います。
- ライセンスの判定は JWT 必須の Edge Function 側で行います。
- ライセンスキーはDBへ平文保存せず、SHA-256ハッシュを保存します。
- 端末識別には初回起動時に生成するランダムな install_id を使い、ハードウェア指紋は採取しません。
- EPUB本文と生成PDF本文はライセンスサーバーへ送信しません。
- PDFへ埋め込む識別情報にメールアドレスや氏名は含めません。

## 配布区分
My Hubでは表示範囲と配布形態を分離します。

- visibility: public / limited / private
- distribution: open / free / beta / commercial

EPUB 縦書き PDF Maker は現在 `limited + beta`、販売予定として管理します。

## 更新配布
`latest-release` Edge Function は、有効なライセンスと更新権限を確認してから最新版情報を返します。実ファイルの恒久配布先は、GitHub ReleasesまたはCloudflare R2等の配布基盤を接続して運用します。

## 顧客別ビルド
GitHub Actions の `Build Windows EXE` を手動実行するときに `customer_code` と `edition` を指定すると、その値をEXE内部へ埋め込めます。通常顧客は共通EXE＋個別ライセンスを使い、学校・法人など必要な場合だけ顧客別ビルドを使う方針です。
