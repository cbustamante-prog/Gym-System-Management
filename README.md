name: Auto Generate README

on:
  push:
    branches: [ main ]

jobs:
  build-readme:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Generate README
        run: |
          echo "# My System" > README.md
          echo "Auto-generated README file" >> README.md
          echo "Last updated: $(date)" >> README.md

      - name: Commit changes
        run: |
          git config --global user.name "github-actions"
          git config --global user.email "actions@github.com"
          git add README.md
          git commit -m "Auto update README" || exit 0
          git push
