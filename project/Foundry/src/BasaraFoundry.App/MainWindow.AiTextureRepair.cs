using System.Net.Http.Headers;
using System.Text.Json;
using BasaraFoundry.Game.Utage.Preview;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics.Imaging;
using Windows.Security.Credentials;
using Windows.Storage.Streams;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private const string FoundryCredentialResource = "BASARA Foundry/OpenAI Image Repair";
    private const string FoundryCredentialUser = "OpenAI API";
    private UtageXetPreviewSnapshot? _currentEnglishPreview;

    private void ClearCurrentEnglishPreview(long generation)
    {
        if (!IsReviewCurrent(generation))
            return;
        _currentEnglishPreview = null;
        GenerateReplacementButton.IsEnabled = false;
    }

    private void SetCurrentEnglishPreview(UtageXetPreviewSnapshot preview, long generation)
    {
        if (!IsReviewCurrent(generation))
            return;
        _currentEnglishPreview = preview;
        RefreshGenerateReplacementAvailability();
    }

    private void RefreshGenerateReplacementAvailability()
    {
        var current = _currentEnglishPreview;
        var pristine = _productionJapanesePreview;
        var donor = _samuraiHeroesProductionPreview;
        var hasCompatibleOfficialDonor =
            donor is { CanEncode: true } &&
            donor.Width == _activeWidth &&
            donor.Height == _activeHeight;
        var hasAiRepairInputs =
            current is not null &&
            pristine is not null &&
            current.Width == _activeWidth && current.Height == _activeHeight &&
            pristine.Width == _activeWidth && pristine.Height == _activeHeight;

        GenerateReplacementButton.IsEnabled =
            _activeResource is not null &&
            _activeWidth > 0 && _activeHeight > 0 &&
            (hasCompatibleOfficialDonor || hasAiRepairInputs);
    }

    private async Task GenerateAiRepairCandidateAsync()
    {
        var current = _currentEnglishPreview
            ?? throw new InvalidOperationException("Current English preview is not available for AI repair.");
        var pristine = _productionJapanesePreview
            ?? throw new InvalidOperationException("Pristine Japanese preview is not available for AI repair.");
        if (current.Width != pristine.Width || current.Height != pristine.Height)
            throw new InvalidDataException("Current English and pristine Japanese atlases have different dimensions.");
        if (current.Rgba.Length != pristine.Rgba.Length)
            throw new InvalidDataException("Current English and pristine Japanese atlases have different RGBA lengths.");

        var repairMask = BuildAutomaticRepairMask(pristine.Rgba, current.Rgba, current.Width, current.Height);
        if (repairMask.ChangedBlocks == 0)
            throw new InvalidDataException(
                "Foundry could not infer an existing English text-repair region from Current ENG versus pristine JP. " +
                "This texture needs an official donor or an explicit translation region before AI generation.");
        if (repairMask.Coverage > 0.35)
            throw new InvalidDataException(
                $"Automatic repair region covers {repairMask.Coverage:P0} of the atlas, which is too broad for a safe one-click edit. " +
                "Foundry refused to let the image model repaint that much artwork.");

        var apiKey = await GetOpenAiApiKeyAsync();
        if (string.IsNullOrWhiteSpace(apiKey))
        {
            SearchStatusText.Text = "AI repair was cancelled; no API credential was stored.";
            return;
        }

        var scale = ChooseGenerationScale(current.Width, current.Height);
        var generatedWidth = checked(current.Width * scale);
        var generatedHeight = checked(current.Height * scale);
        var pristineLarge = UpscaleNearest(pristine.Rgba, current.Width, current.Height, scale);
        var currentLarge = UpscaleNearest(current.Rgba, current.Width, current.Height, scale);
        var maskLarge = UpscaleMask(repairMask.Mask01, current.Width, current.Height, scale);
        var apiMaskRgba = BuildApiMaskRgba(maskLarge);

        var pristinePng = await EncodePngAsync(pristineLarge, generatedWidth, generatedHeight);
        var currentPng = await EncodePngAsync(currentLarge, generatedWidth, generatedHeight);
        var maskPng = await EncodePngAsync(apiMaskRgba, generatedWidth, generatedHeight);

        var projectDir = Path.GetDirectoryName(_projectPath)!;
        var requestId = Guid.NewGuid().ToString("N");
        var aiDir = Path.Combine(projectDir, "cache", "ai-texture-repair", requestId);
        Directory.CreateDirectory(aiDir);
        await File.WriteAllBytesAsync(Path.Combine(aiDir, "01-pristine-jp.png"), pristinePng);
        await File.WriteAllBytesAsync(Path.Combine(aiDir, "02-current-eng-wording-reference.png"), currentPng);
        await File.WriteAllBytesAsync(Path.Combine(aiDir, "03-edit-mask.png"), maskPng);

        SearchStatusText.Text =
            $"Generating polished English artwork in {repairMask.ChangedBlocks:N0} inferred text blocks; " +
            "everything outside that region will be restored from pristine JP exactly…";

        var generatedPng = await RequestOpenAiTextureEditAsync(
            apiKey,
            pristinePng,
            currentPng,
            maskPng,
            generatedWidth,
            generatedHeight);
        await File.WriteAllBytesAsync(Path.Combine(aiDir, "04-model-output.png"), generatedPng);

        var generatedLarge = await DecodeExactRgbaAsync(generatedPng, generatedWidth, generatedHeight);
        var generatedSmall = DownsampleBox(generatedLarge, generatedWidth, generatedHeight, scale);
        var lockedCandidate = CompositeOnlyMask(pristine.Rgba, generatedSmall, repairMask.Mask01);
        await File.WriteAllBytesAsync(Path.Combine(aiDir, "05-locked-candidate.rgba"), lockedCandidate);

        var outsideDelta = CountOutsideMaskDelta(pristine.Rgba, lockedCandidate, repairMask.Mask01);
        if (outsideDelta != 0)
            throw new InvalidDataException($"AI repair isolation failed: {outsideDelta} protected pixels changed after hard compositing.");

        await AttachGeneratedCandidateAsync(
            lockedCandidate,
            $"AI polished repair · {repairMask.ChangedBlocks:N0} text blocks",
            "AI REPAIR · PROTECTED ART LOCKED");
        SearchStatusText.Text =
            $"AI replacement ready · {repairMask.ChangedBlocks:N0} inferred text blocks · " +
            "0 protected pixels changed. Review the replacement art before building it.";
    }

    private async Task<string?> GetOpenAiApiKeyAsync()
    {
        var environment = Environment.GetEnvironmentVariable("OPENAI_API_KEY");
        if (!string.IsNullOrWhiteSpace(environment))
            return environment.Trim();

        try
        {
            var vault = new PasswordVault();
            var credential = vault.Retrieve(FoundryCredentialResource, FoundryCredentialUser);
            credential.RetrievePassword();
            if (!string.IsNullOrWhiteSpace(credential.Password))
                return credential.Password;
        }
        catch
        {
            // First use or unavailable credential locker; prompt below.
        }

        var keyBox = new PasswordBox
        {
            PlaceholderText = "OpenAI API key",
            MinWidth = 520,
        };
        var content = new StackPanel { Spacing = 10 };
        content.Children.Add(new TextBlock
        {
            Text = "Utage-only texture repair uses the OpenAI image-edit API. Enter an API key once; Foundry stores it in Windows Credential Manager, not in the project or GitHub. Your normal ChatGPT sign-in is not copied into this standalone app.",
            TextWrapping = Microsoft.UI.Xaml.TextWrapping.Wrap,
        });
        content.Children.Add(keyBox);
        var dialog = new ContentDialog
        {
            XamlRoot = WorkspacePanel.XamlRoot,
            Title = "Enable one-click AI texture repair",
            PrimaryButtonText = "Save and generate",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary,
            Content = content,
        };
        var result = await dialog.ShowAsync();
        if (result != ContentDialogResult.Primary)
            return null;

        var key = keyBox.Password.Trim();
        if (string.IsNullOrWhiteSpace(key))
            throw new InvalidDataException("API key was empty.");

        try
        {
            var vault = new PasswordVault();
            try
            {
                var existing = vault.Retrieve(FoundryCredentialResource, FoundryCredentialUser);
                vault.Remove(existing);
            }
            catch { }
            vault.Add(new PasswordCredential(FoundryCredentialResource, FoundryCredentialUser, key));
        }
        catch (Exception ex)
        {
            throw new InvalidDataException($"Windows Credential Manager did not accept the API key: {ex.Message}");
        }
        return key;
    }

    private static async Task<byte[]> RequestOpenAiTextureEditAsync(
        string apiKey,
        byte[] pristinePng,
        byte[] currentEnglishPng,
        byte[] maskPng,
        int width,
        int height)
    {
        const string prompt =
            "Repair this Sengoku BASARA 3 Utage localization texture atlas. " +
            "IMAGE 1 is the pristine Japanese artwork and is the visual authority. " +
            "IMAGE 2 is the current English patch and is reference ONLY for the intended English wording and which Japanese labels were being replaced; do not copy its poor typography or damaged artwork. " +
            "Edit ONLY the transparent mask areas. Replace the Japanese lettering there with polished, fully legible English using the wording shown in image 2 wherever present. " +
            "Match the original Japanese artwork's professional Capcom UI typography, brush/ink character, weight, outline, bevel, glow, shadow, spacing and visual hierarchy. " +
            "Preserve every card, seal, symbol, gradient, border, background, alpha edge, sprite coordinate and decorative element. " +
            "Do not invent new graphics. Keep every English label completely inside the original sprite slot. The result must remain a texture atlas, not a poster or mockup.";

        using var client = new HttpClient { Timeout = TimeSpan.FromMinutes(3) };
        using var request = new HttpRequestMessage(HttpMethod.Post, "https://api.openai.com/v1/images/edits");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        using var form = new MultipartFormDataContent();
        form.Add(new StringContent("gpt-image-2.5-sunburst"), "model");
        form.Add(new StringContent(prompt), "prompt");
        form.Add(new StringContent($"{width}x{height}"), "size");
        form.Add(new StringContent("max"), "quality");
        form.Add(new StringContent("png"), "output_format");
        form.Add(PngPart(pristinePng), "image[]", "pristine-jp.png");
        form.Add(PngPart(currentEnglishPng), "image[]", "current-eng-reference.png");
        form.Add(PngPart(maskPng), "mask", "edit-mask.png");
        request.Content = form;

        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseContentRead);
        var body = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
        {
            string detail = $"HTTP {(int)response.StatusCode}";
            try
            {
                using var errorJson = JsonDocument.Parse(body);
                if (errorJson.RootElement.TryGetProperty("error", out var error) &&
                    error.TryGetProperty("message", out var message))
                    detail = message.GetString() ?? detail;
            }
            catch { }
            throw new InvalidDataException($"Image generation service rejected the texture repair: {detail}");
        }

        using var json = JsonDocument.Parse(body);
        if (!json.RootElement.TryGetProperty("data", out var data) || data.GetArrayLength() < 1 ||
            !data[0].TryGetProperty("b64_json", out var encoded))
            throw new InvalidDataException("Image generation service returned no image data.");
        var base64 = encoded.GetString();
        if (string.IsNullOrWhiteSpace(base64))
            throw new InvalidDataException("Image generation service returned an empty image.");
        try
        {
            return Convert.FromBase64String(base64);
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException("Image generation service returned invalid base64 image data.", ex);
        }
    }

    private static ByteArrayContent PngPart(byte[] bytes)
    {
        var part = new ByteArrayContent(bytes);
        part.Headers.ContentType = new MediaTypeHeaderValue("image/png");
        return part;
    }

    private sealed record AutomaticRepairMask(byte[] Mask01, int ChangedBlocks, double Coverage);

    private static AutomaticRepairMask BuildAutomaticRepairMask(byte[] pristine, byte[] current, int width, int height)
    {
        if (pristine.Length != current.Length || pristine.Length != checked(width * height * 4))
            throw new ArgumentException("Atlas RGBA inputs do not match dimensions.");
        var blocksX = (width + 3) / 4;
        var blocksY = (height + 3) / 4;
        var raw = new bool[blocksX * blocksY];

        for (var by = 0; by < blocksY; by++)
        for (var bx = 0; bx < blocksX; bx++)
        {
            var strong = 0;
            var score = 0;
            for (var py = by * 4; py < Math.Min(height, by * 4 + 4); py++)
            for (var px = bx * 4; px < Math.Min(width, bx * 4 + 4); px++)
            {
                var p = (py * width + px) * 4;
                var delta = Math.Max(
                    Math.Max(Math.Abs(pristine[p] - current[p]), Math.Abs(pristine[p + 1] - current[p + 1])),
                    Math.Max(Math.Abs(pristine[p + 2] - current[p + 2]), Math.Abs(pristine[p + 3] - current[p + 3])));
                if (delta >= 32)
                    strong++;
                score += delta;
            }
            raw[by * blocksX + bx] = strong >= 2 || score >= 320;
        }

        var dilated = new bool[raw.Length];
        for (var by = 0; by < blocksY; by++)
        for (var bx = 0; bx < blocksX; bx++)
        {
            if (!raw[by * blocksX + bx])
                continue;
            for (var dy = -1; dy <= 1; dy++)
            for (var dx = -1; dx <= 1; dx++)
            {
                var nx = bx + dx;
                var ny = by + dy;
                if (nx >= 0 && nx < blocksX && ny >= 0 && ny < blocksY)
                    dilated[ny * blocksX + nx] = true;
            }
        }

        var mask = new byte[width * height];
        var changedBlocks = 0;
        for (var by = 0; by < blocksY; by++)
        for (var bx = 0; bx < blocksX; bx++)
        {
            if (!dilated[by * blocksX + bx])
                continue;
            changedBlocks++;
            for (var py = by * 4; py < Math.Min(height, by * 4 + 4); py++)
            for (var px = bx * 4; px < Math.Min(width, bx * 4 + 4); px++)
                mask[py * width + px] = 1;
        }

        return new AutomaticRepairMask(mask, changedBlocks, changedBlocks / (double)(blocksX * blocksY));
    }

    private static int ChooseGenerationScale(int width, int height)
    {
        for (var scale = 1; scale <= 16; scale++)
        {
            var w = checked(width * scale);
            var h = checked(height * scale);
            var pixels = (long)w * h;
            if (w > 3840 || h > 3840)
                break;
            if (w % 16 == 0 && h % 16 == 0 && pixels >= 655_360 && pixels <= 8_294_400 &&
                Math.Max(w, h) <= 3 * Math.Min(w, h))
                return scale;
        }
        throw new NotSupportedException($"Texture {width}×{height} cannot be mapped to a safe image-generation resolution without changing aspect ratio.");
    }

    private static byte[] UpscaleNearest(byte[] rgba, int width, int height, int scale)
    {
        var outWidth = checked(width * scale);
        var outHeight = checked(height * scale);
        var result = new byte[checked(outWidth * outHeight * 4)];
        for (var y = 0; y < outHeight; y++)
        for (var x = 0; x < outWidth; x++)
        {
            var source = ((y / scale) * width + (x / scale)) * 4;
            var dest = (y * outWidth + x) * 4;
            Buffer.BlockCopy(rgba, source, result, dest, 4);
        }
        return result;
    }

    private static byte[] UpscaleMask(byte[] mask, int width, int height, int scale)
    {
        var outWidth = checked(width * scale);
        var outHeight = checked(height * scale);
        var result = new byte[checked(outWidth * outHeight)];
        for (var y = 0; y < outHeight; y++)
        for (var x = 0; x < outWidth; x++)
            result[y * outWidth + x] = mask[(y / scale) * width + (x / scale)];
        return result;
    }

    private static byte[] BuildApiMaskRgba(byte[] mask01)
    {
        var rgba = new byte[checked(mask01.Length * 4)];
        for (var i = 0; i < mask01.Length; i++)
        {
            var p = i * 4;
            rgba[p] = rgba[p + 1] = rgba[p + 2] = 255;
            rgba[p + 3] = mask01[i] == 0 ? (byte)255 : (byte)0;
        }
        return rgba;
    }

    private static byte[] DownsampleBox(byte[] rgba, int width, int height, int scale)
    {
        if (width % scale != 0 || height % scale != 0)
            throw new ArgumentException("Generated dimensions are not divisible by the source scale.");
        var outWidth = width / scale;
        var outHeight = height / scale;
        var result = new byte[checked(outWidth * outHeight * 4)];
        var samples = scale * scale;
        for (var oy = 0; oy < outHeight; oy++)
        for (var ox = 0; ox < outWidth; ox++)
        {
            Span<int> totals = stackalloc int[4];
            for (var dy = 0; dy < scale; dy++)
            for (var dx = 0; dx < scale; dx++)
            {
                var p = (((oy * scale + dy) * width) + ox * scale + dx) * 4;
                totals[0] += rgba[p];
                totals[1] += rgba[p + 1];
                totals[2] += rgba[p + 2];
                totals[3] += rgba[p + 3];
            }
            var d = (oy * outWidth + ox) * 4;
            for (var c = 0; c < 4; c++)
                result[d + c] = (byte)((totals[c] + samples / 2) / samples);
        }
        return result;
    }

    private static byte[] CompositeOnlyMask(byte[] pristine, byte[] generated, byte[] mask01)
    {
        if (pristine.Length != generated.Length || pristine.Length != checked(mask01.Length * 4))
            throw new ArgumentException("Composite inputs do not have matching dimensions.");
        var result = (byte[])pristine.Clone();
        for (var i = 0; i < mask01.Length; i++)
        {
            if (mask01[i] == 0)
                continue;
            Buffer.BlockCopy(generated, i * 4, result, i * 4, 4);
        }
        return result;
    }

    private static int CountOutsideMaskDelta(byte[] pristine, byte[] candidate, byte[] mask01)
    {
        var changed = 0;
        for (var i = 0; i < mask01.Length; i++)
        {
            if (mask01[i] != 0)
                continue;
            var p = i * 4;
            if (pristine[p] != candidate[p] || pristine[p + 1] != candidate[p + 1] ||
                pristine[p + 2] != candidate[p + 2] || pristine[p + 3] != candidate[p + 3])
                changed++;
        }
        return changed;
    }

    private static async Task<byte[]> EncodePngAsync(byte[] rgba, int width, int height)
    {
        using var stream = new InMemoryRandomAccessStream();
        var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream);
        encoder.SetPixelData(
            BitmapPixelFormat.Rgba8,
            BitmapAlphaMode.Straight,
            (uint)width,
            (uint)height,
            96,
            96,
            rgba);
        await encoder.FlushAsync();
        stream.Seek(0);
        using var reader = new DataReader(stream.GetInputStreamAt(0));
        await reader.LoadAsync((uint)stream.Size);
        var bytes = new byte[checked((int)stream.Size)];
        reader.ReadBytes(bytes);
        return bytes;
    }

    private static async Task<byte[]> DecodeExactRgbaAsync(byte[] png, int expectedWidth, int expectedHeight)
    {
        using var stream = new InMemoryRandomAccessStream();
        using (var writer = new DataWriter(stream.GetOutputStreamAt(0)))
        {
            writer.WriteBytes(png);
            await writer.StoreAsync();
            await writer.FlushAsync();
        }
        stream.Seek(0);
        var decoder = await BitmapDecoder.CreateAsync(stream);
        if ((int)decoder.PixelWidth != expectedWidth || (int)decoder.PixelHeight != expectedHeight)
            throw new InvalidDataException(
                $"Image model returned {decoder.PixelWidth}×{decoder.PixelHeight}; expected {expectedWidth}×{expectedHeight}. Foundry refused to remap atlas coordinates.");
        var pixels = await decoder.GetPixelDataAsync(
            BitmapPixelFormat.Rgba8,
            BitmapAlphaMode.Straight,
            new BitmapTransform(),
            ExifOrientationMode.IgnoreExifOrientation,
            ColorManagementMode.DoNotColorManage);
        var rgba = pixels.DetachPixelData();
        if (rgba.Length != checked(expectedWidth * expectedHeight * 4))
            throw new InvalidDataException("Image model PNG decoded to an unexpected RGBA length.");
        return rgba;
    }
}
