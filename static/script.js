// Client-side JavaScript for AI legal arguments app

let pipelineCancelled = false

function setControlsEnabled(enabled) {
    document.getElementById("uploadBtn").disabled = !enabled
    document.getElementById("generateBtn").disabled = !enabled
    document.getElementById("validateBtn").disabled = !enabled
    document.getElementById("downloadBtn").disabled = !enabled
}

function showSpinner(active) {
    let spinner = document.getElementById("spinner")
    if (!spinner) return
    spinner.classList.toggle("hidden", !active)
}

function appendLog(message) {
    let log = document.getElementById("log")
    if (!log) return
    let ts = new Date().toLocaleTimeString()
    log.innerText += `\n[${ts}] ${message}`
    log.scrollTop = log.scrollHeight
}

function cancelPipeline() {
    pipelineCancelled = true
    setControlsEnabled(true)
    showSpinner(false)
    let status = document.getElementById("status")
    status.innerText = "Pipeline cancelled"
    appendLog("Pipeline cancellation requested by user")
}

function resetPipelineState() {
    pipelineCancelled = false
    appendLog("Pipeline state reset")
}

async function upload(){
    resetPipelineState()
    showSpinner(true)
    let status = document.getElementById("status")
    status.innerText = "Uploading..."
    appendLog("Upload started")
    setControlsEnabled(false)
    console.info('Upload initiated')

    try {
        let file = document.getElementById("file").files[0]
        if (!file) throw new Error('No file selected')

        let form = new FormData()
        form.append("file", file)

        let response = await fetch("/upload", { method: "POST", body: form })
        let result = await response.json()

        if (!response.ok || result.status === "error") {
            let errorMsg = result.message || 'Upload failed'
            console.error('Upload error', errorMsg)
            status.innerText = "Upload failed"
            alert(errorMsg)
            return { success: false }
        }

        console.info('Upload successful', result)
        status.innerText = "Uploaded"
        appendLog("Upload successful")

        // Auto run complete pipeline sequentially
        await runFullPipeline()

        return { success: true }
    } catch (err) {
        console.error('Upload exception', err)
        status.innerText = "Upload failed"
        appendLog(`Upload exception: ${err.message}`)
        alert('Upload failed: ' + err.message)
        return { success: false }
    } finally {
        showSpinner(false)
        setControlsEnabled(true)
    }
}

async function runFullPipeline(){
    let status = document.getElementById("status")
    status.innerText = "Running automated pipeline: generate → validate → download..."
    appendLog("Pipeline started")
    showSpinner(true)

    if (pipelineCancelled) {
        status.innerText = "Pipeline cancelled"
        appendLog("Pipeline aborted before generate")
        showSpinner(false)
        return
    }

    let genResult = await generate()
    if (!genResult.success || pipelineCancelled) {
        appendLog("Pipeline aborted after generate")
        showSpinner(false)
        return
    }

    status.innerText = "Pipeline: validation in progress"
    let valResult = await validate()
    if (!valResult.success || pipelineCancelled) {
        appendLog("Pipeline aborted after validate")
        showSpinner(false)
        return
    }

    status.innerText = "Pipeline: downloading PDF"
    let dlResult = await download()
    if (!dlResult.success || pipelineCancelled) {
        appendLog("Pipeline aborted after download")
        showSpinner(false)
        return
    }

    status.innerText = "Pipeline completed successfully"
    appendLog("Pipeline completed successfully")
    showSpinner(false)
    console.info('Automated pipeline completed')
}

async function validate(){
    let status = document.getElementById("status")
    status.innerText = "Starting validation..."
    console.info('Validation initiated')

    try {
        // Step 1: Start the validation task
        let startRes = await fetch("/validate/start", { method: "POST" })
        let startData = await startRes.json()

        if (!startRes.ok || startData.status === "error") {
            throw new Error(startData.message || 'Failed to start validation')
        }

        let taskId = startData.task_id
        console.info('Validation task started with task_id=%s', taskId)
        status.innerText = "Validation in progress (polling Gemini)..."

        return new Promise((resolve) => {
            let pollInterval = setInterval(async () => {
                try {
                    let statusRes = await fetch(`/validate/status/${taskId}`)
                    let statusData = await statusRes.json()

                    console.debug('Validation poll result for task_id=%s: %s', taskId, statusData.status)

                    if (pipelineCancelled) {
                        clearInterval(pollInterval)
                        status.innerText = "Validation cancelled"
                        appendLog("Validation pipeline cancelled")
                        setControlsEnabled(true)
                        showSpinner(false)
                        resolve({ success: false })
                        return
                    }

                    if (statusData.status === "pending") {
                        status.innerText = "Validation in progress (polling Gemini)... Please wait"
                        return
                    }

                    clearInterval(pollInterval)

                    if (statusData.status === "error") {
                        console.error('Validation task error', statusData.error)
                        status.innerText = "Validation failed"
                        appendLog(`Validation task error: ${statusData.error}`)
                        alert('Validation error: ' + statusData.error)
                        setControlsEnabled(true)
                        showSpinner(false)
                        resolve({ success: false })
                        return
                    }

                    if (statusData.status === "complete") {
                        console.info('Validation task completed', statusData.result)
                        appendLog('Validation task completed')

                        let validationData = typeof statusData.result === 'string' ? JSON.parse(statusData.result) : statusData.result

                        let validationText = `VALIDATION REPORT\n\nOverall Validity Score: ${validationData.overall_validity_score}/10\nLogic Score: ${validationData.logic_score}/10\nCitation Validity Score: ${validationData.citation_validity_score}/10\n\nIssues Found:\n${validationData.issues_found.map(issue => `- ${issue}`).join('\n')}\n\nSuggested Improvements:\n${validationData.suggested_improvements.map(improvement => `- ${improvement}`).join('\n')}\n\nHallucinated Citations:\n${validationData.hallucinated_citations.map(citation => `- ${citation}`).join('\n')}`

                        document.getElementById("validation").innerText = validationText
                        status.innerText = "Validation complete"
                        setControlsEnabled(true)
                        resolve({ success: true })
                    }
                } catch (pollErr) {
                    console.error('Poll request error', pollErr)
                    appendLog(`Validation polling error: ${pollErr.message}`)
                    clearInterval(pollInterval)
                    status.innerText = "Validation failed"
                    setControlsEnabled(true)
                    showSpinner(false)
                    alert('Validation polling error: ' + pollErr.message)
                    resolve({ success: false })
                }
            }, 2000)  // Poll every 2 seconds
        })

    } catch (err) {
        console.error('Validation start exception', err)
        appendLog(`Validation start exception: ${err.message}`)
        status.innerText = "Validation failed"
        setControlsEnabled(true)
        showSpinner(false)
        alert('Validation failed: ' + err.message)
        return { success: false }
    }
}

async function generate(){
    let status = document.getElementById("status")
    status.innerText = "Generating..."
    console.info('Analyze + build argument initiated')
    setControlsEnabled(false)

    try {
        let res = await fetch("/analyze", { method: "POST" })
        let data = await res.json()

        if (!res.ok || data.status === "error") {
            throw new Error(data.message || 'Analysis failed')
        }

        console.info('Analysis results', data)
        appendLog('Generation completed successfully')
        status.innerText = "Done"

        document.getElementById("output").innerText = data.text

        let div = document.getElementById("citations")
        div.innerHTML = ""

        data.citations.forEach((c) => {
            let btn = document.createElement("button")
            btn.innerText = c.case_name
            btn.onclick = () => {
                alert(
                    "Description:" + c.description +
                    "\nWhy cited:" + c.why_cited +
                    "\nRelevance:" + c.relevance_score +
                    "\nStrength:" + c.strength_score +
                    "\nLink:" + c.link
                )
            }
            div.appendChild(btn)
        })

        return { success: true }
    } catch (err) {
        console.error('Generate exception', err)
        appendLog(`Generate exception: ${err.message}`)
        status.innerText = "Generation failed"
        alert('Generation failed: ' + err.message)
        return { success: false }
    } finally {
        setControlsEnabled(true)
        showSpinner(false)
    }
}

async function download(){
    let status = document.getElementById("status")
    status.innerText = "Generating PDF..."
    console.info('PDF download initiated')
    setControlsEnabled(false)

    try {
        let res = await fetch("/generate_pdf", { method: "POST" })

        if (!res.ok) {
            let error = await res.json().catch(() => ({}))
            console.error('PDF generation error', error)
            status.innerText = "PDF generation failed"
            alert('Error generating PDF: ' + (error.message || 'Unknown'))
            setControlsEnabled(true)
            return { success: false }
        }

        let filename = "legal_argument.pdf"
        let contentDisposition = res.headers.get("content-disposition")
        if (contentDisposition) {
            let match = contentDisposition.match(/filename="?(.*)"?$/)
            if (match && match[1]) filename = match[1]
        }

        let blob = await res.blob()
        let url = URL.createObjectURL(blob)
        let a = document.createElement("a")
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)

        console.info('PDF downloaded', filename)
        appendLog(`Download success: ${filename}`)
        status.innerText = `PDF generated: ${filename}. Saved in your browser downloads folder.`
        setControlsEnabled(true)
        showSpinner(false)
        return { success: true }
    } catch (err) {
        console.error('Download exception', err)
        appendLog(`Download exception: ${err.message}`)
        status.innerText = "PDF generation failed"
        setControlsEnabled(true)
        showSpinner(false)
        alert('PDF generation failed: ' + err.message)
        return { success: false }
    }
}

