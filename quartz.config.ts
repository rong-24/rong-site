import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * Quartz 4 Configuration
 *
 * See https://quartz.jzhao.xyz/configuration for more information.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "Rong's Digital Garden",
    pageTitleSuffix: "",
    enableSPA: true,// Set to false to disable client-side navigation and page transitions
    enablePopovers: true,// Set to false to disable the "Copy Link" button in the popover
    analytics: null, // Add your analytics tracking code here (e.g., Google Analytics, Plausible)
    locale: "zh-CN",
    baseUrl: "rong-24.github.io/rong-site",// The base URL of your site, used for generating absolute URLs for assets and links
    ignorePatterns: ["private", "templates", ".obsidian"],// An array of glob patterns to exclude files or folders from the build process
    defaultDateType: "modified",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      
      typography: {// Customize your site's typography by specifying fonts for headers, body text, and code blocks
        header: "Schibsted Grotesk",
        body: "Source Sans Pro",
        code: "IBM Plex Mono",
      },
      
      colors: {// Define color schemes for light and dark modes, including primary, secondary, and highlight colors
        lightMode: {
          light: "#faf8f8",
          lightgray: "#e5e5e5",
          gray: "#b8b8b8",
          darkgray: "#4e4e4e",
          dark: "#2b2b2b",
          secondary: "#284b63",
          tertiary: "#84a59d",
          highlight: "rgba(143, 159, 169, 0.15)",
          textHighlight: "#fff23688",
        },
        darkMode: {
          light: "#161618",
          lightgray: "#393639",
          gray: "#646464",
          darkgray: "#d4d4d4",
          dark: "#ebebec",
          secondary: "#7b97aa",
          tertiary: "#84a59d",
          highlight: "rgba(143, 159, 169, 0.15)",
          textHighlight: "#b3aa0288",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),// Extract metadata from the front matter of markdown files and make it available for use in templates and other plugins
      Plugin.CreatedModifiedDate({// Automatically extract created and modified dates for content files using multiple strategies, including front matter, Git history, and filesystem timestamps
        priority: ["frontmatter", "git", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({// Add syntax highlighting to code blocks in markdown files using Shiki, with support for light and dark themes
        theme: {
          light: "github-light",
          dark: "github-dark",
        },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts()],// Exclude markdown files with "draft: true" in their front matter from the build output
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: true,
        enableRSS: true,
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
      // Comment out CustomOgImages to speed up build time
      //Plugin.CustomOgImages(),
    ],
  },
}

export default config
