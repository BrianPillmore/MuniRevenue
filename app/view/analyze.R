box::use(
  shiny,
  bslib,
  rmarkdown,
  shinyjs,
)


#' @export
ui <- function(id) {
  ns <- shiny$NS(id)
  shiny$tagList(

    bslib$page_fluid(
      shiny$br(), shiny$br(),
      shiny$tags$p(
        "Please upload the tax data for your city to generate a comprehensive PDF report.
        The report will include detailed analysis and visualizations of the city's tax revenues.
        If you need a reference, you can download sample data and an example report using the links below.
        The sample data will give you an idea of the required format, and the example report will show you what to expect
        in terms of insights and information. Ensure that your data is formatted correctly before uploading
        to avoid any issues during the report generation."
      ),
      bslib$layout_columns(
  
        shiny$downloadButton(ns("sample"),"Sample data"),
        shiny$downloadButton(ns("sampleReport"),"Sample report"),
        "",
        "",
        "",
        ""

      ),
      shiny$fileInput(ns('file'), 'Choose Excel (.xlsx) File:',
      accept=c('xlsx')),
      shiny$downloadButton(ns("report"), "PDF Report"),

    )
  )
}

#' @export
server <- function(id) {
  shiny$moduleServer(id, function(input, output, session) {
    ns <- session$ns
    shinyjs$hide("report")

    shiny$observeEvent(input$file$datapath,{
      Sys.sleep(1.5)
      shinyjs$show("report")
    })

    output$report <- shiny$downloadHandler(
      "TaxReport.pdf",
      content =
        function(file) {
          shiny$withProgress(
            message = "Downloading the pdf report",
            value = 1/3,
            {
              rmarkdown$render(
                input = "app/logic/report.Rmd",
                output_file = "built_report.pdf",
                params = list(
                  data = input$file$datapath
                )
              )
              readBin(
                con = "app/logic/built_report.pdf",
                what = "raw",
                n = file.info("app/logic/built_report.pdf")[, "size"]
              ) |>
                writeBin(con = file)
            }
          )
        }
    )

    output$sample <- shiny$downloadHandler(
      filename = function() {
        "SampleData.xlsx"  # The name of the file the user will download
      },
      content = function(file) {
        # Copy the file from your app's static directory to the 'file' location
        file.copy("app/static/SampleData.xlsx", file)
      }
    )

    output$sampleReport <- shiny$downloadHandler(
      filename = function() {
        "SampleReport.pdf"  # The name of the file the user will download
      },
      content = function(file) {
        # Copy the file from your app's static directory to the 'file' location
        file.copy("app/static/SampleReport.pdf", file)
      }
    )

  })
}
