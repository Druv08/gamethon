// Protect the King - 2D. The one reusable projectile.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Core/PTKTypes.h"
#include "PTKProjectile.generated.h"

class UPaperFlipbook;
class UPaperFlipbookComponent;
class USphereComponent;

/**
 * APTKProjectile
 * ==============
 * Anything a character fires: Wraith's arrow today, and whatever Sentinel or a
 * ranged enemy throws later. Nothing in here knows what a Wraith is.
 *
 *
 * WHY THIS IS NOT THE MELEE PATH
 * ------------------------------
 * APTKTopDownCharacter::PerformAttackHit() resolves a swing instantly: it
 * overlaps a sphere placed in front of the character and damages what it finds,
 * in the same frame the impact pose is reached. That is right for an axe and
 * wrong for a bow. An arrow has to leave the bow, cross the gap, and damage
 * whatever it actually reaches - so the shot can miss, can be outrun, and can
 * strike something that walked into its path after it was loosed.
 *
 * So a firing character does not run the melee test at all. It spawns one of
 * these at the release frame and hands over; damage is this actor's business
 * from then on, and it happens where the arrow is, not where the archer is.
 *
 *
 * WHO IT CAN HURT
 * ---------------
 * OwningTeam is the side that fired, and hostility is PTKCombat::AreHostile -
 * the same rule the melee path uses. For a guard's arrow that means enemies
 * only: it cannot hit the archer, another guard, or the King, because Guards
 * and King are different teams but the same side. Getting this from the shared
 * helper rather than from a local team check is the point - a second opinion
 * about who is an ally is exactly how friendly fire gets in.
 *
 *
 * IT FLIES AT THE COMBAT ROW, AND IS DRAWN ABOVE IT
 * -------------------------------------------------
 * This is the one thing that has to be right, and it was wrong to begin with.
 *
 * Every gameplay footprint in this project sits at the actor's own row: a
 * Swarm Node's collision is an 18-unit blob at its feet, and the melee sphere
 * is built from GetActorLocation() with no vertical offset. Sprites are then
 * DRAWN upward from that row - which is why a character standing level with
 * you overlaps you on screen even though the collision is only at the feet.
 *
 * The arrow originally spawned 70 units up, at the bow. That reads correctly
 * but put the actor - and therefore the sweep - on a row 70 above everything
 * it was aimed at, and 70 is more than the 18 + 8 the two radii can close. An
 * enemy standing level with the archer was literally unhittable. Measured over
 * 104 live shots: firing DOWN hit 71% (the arrow descends through the row),
 * UP hit 10% (it climbs away), and level shots 32% (they connect only with an
 * enemy who happens to be ~70 higher up the screen).
 *
 * So the actor flies at the shooter's own row, and VisualHeightOffset lifts
 * only the SPRITE to bow height. Both the arrow and its target are then drawn
 * up from the same row, so what you see crossing an enemy is what collides
 * with it.
 *
 *
 * ONE ARROW, ONE HIT PER ENEMY
 * ----------------------------
 * The flight sweeps from last position to next rather than relying on overlap
 * events, so nothing is missed between frames however fast it travels, and the
 * FIRST valid blocking hit detonates it. Detonation damages every hostile
 * within SplashRadius exactly once, tracked in a set, and the projectile is
 * spent immediately afterwards - so no enemy can be damaged twice by one
 * arrow, however the blast overlaps them.
 *
 * Piercing - continuing THROUGH a body to strike another behind it - is still
 * not implemented. Splash is not piercing: the arrow stops where it lands.
 */
UCLASS(Blueprintable)
class PROTECTTHEKING2D_API APTKProjectile : public AActor
{
	GENERATED_BODY()

public:
	APTKProjectile();

	virtual void Tick(float DeltaSeconds) override;
	virtual void BeginPlay() override;

	/**
	 * Arms and launches the projectile. Call immediately after spawning.
	 *
	 * Everything the projectile needs is passed in rather than read off the
	 * shooter, so it stays independent of what fired it - and so a Blueprint
	 * can fire one without being a PTK character at all.
	 *
	 * @param InDirection  Unit direction of travel, in WORLD space. The caller
	 *                     builds this from the camera-derived screen basis; the
	 *                     projectile never assumes which world axis is
	 *                     screen-right. See APTKTopDownCharacter.
	 * @param InFacing     Which of the four directional flipbooks to draw.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Projectile")
	void Launch(const FVector& InDirection, EPTKFacingDirection InFacing,
		AActor* InSource, EPTKTeam InOwningTeam, float InDamage,
		float InSpeed, float InRange, float InVisualHeight, const FVector& InUpVector);

	UFUNCTION(BlueprintPure, Category = "PTK|Projectile")
	AActor* GetSourceActor() const { return SourceActor; }

	UFUNCTION(BlueprintPure, Category = "PTK|Projectile")
	EPTKTeam GetOwningTeam() const { return OwningTeam; }

	/** True once it has struck something or run out of range. */
	UFUNCTION(BlueprintPure, Category = "PTK|Projectile")
	bool IsSpent() const { return bSpent; }

	/** Optional shot-specific target lock. Unset preserves existing guard shots. */
	void SetIntendedTarget(AActor* InTarget) { IntendedTarget = InTarget; bTargetRestricted = true; }

protected:
	TWeakObjectPtr<AActor> IntendedTarget;
	bool bTargetRestricted = false;

	/** Fired when the arrow damages something. Prototype hook for VFX / audio. */
	UFUNCTION(BlueprintImplementableEvent, Category = "PTK|Projectile")
	void OnProjectileHit(AActor* Victim, float DamageDealt);

	/**
	 * Damages every hostile within SplashRadius of the blast, once each.
	 *
	 * Returns how many were hit. All damage goes through here, including the
	 * body the arrow physically struck - it is inside its own blast - so there
	 * is exactly one place that can damage anything, and the once-per-enemy
	 * rule is a property of that one place rather than of two paths agreeing.
	 */
	int32 ApplySplash(const FVector& AtLocation, AActor* DirectVictim);

	/**
	 * Stops the flight, plays the impact flipbook and schedules destruction.
	 *
	 * `DirectVictim` is null when the projectile simply ran out of range, which
	 * is why the two endings share one function - an expiring shot must clean
	 * itself up exactly as thoroughly as one that hit, but must not deal damage
	 * on the way out.
	 */
	void Expire(AActor* DirectVictim, const FVector& AtLocation);

	/** Query sphere. Also the root - the sprite hangs off it. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Components")
	TObjectPtr<USphereComponent> Collision;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Components")
	TObjectPtr<UPaperFlipbookComponent> Sprite;

	// ------------------------------------------------------------------
	// Art
	// ------------------------------------------------------------------

	/**
	 * The arrow in flight, one flipbook per direction.
	 *
	 * Four separate flipbooks rather than one rotated sprite: the frames are
	 * exact 90-degree rotations baked at extraction time, which is lossless,
	 * where rotating the component would resample pixel art at runtime.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile|Art")
	FPTKDirectionalFlipbooks FlightFlipbooks;

	/**
	 * The burst on impact. Non-directional, because it is radial.
	 * Left empty, the projectile simply vanishes on hit.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile|Art")
	TObjectPtr<UPaperFlipbook> ImpactFlipbook;

	/** Seconds the impact is given to play before the actor is destroyed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile|Art", meta = (ClampMin = "0.0"))
	float ImpactLifetime = 0.35f;

	// ------------------------------------------------------------------
	// Flight
	// ------------------------------------------------------------------

	/** World units per second. Overwritten by Launch. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile", meta = (ClampMin = "1.0"))
	float Speed = 900.0f;

	/** Damage dealt to the first valid victim. Overwritten by Launch. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile", meta = (ClampMin = "0.0"))
	float Damage = 30.0f;

	/**
	 * How far it may travel before expiring, in world units.
	 *
	 * This is the shooter's attack range, not a separate lifetime: an arrow
	 * that outlived its stated reach would let a 7-tile character kill at 12,
	 * and the debug range ring would be a lie. Overwritten by Launch.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile", meta = (ClampMin = "1.0"))
	float MaxRange = 448.0f;

	/** Radius of the flight sweep - how near the arrow must pass to connect. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile", meta = (ClampMin = "1.0"))
	float CollisionRadius = 12.0f;

	/**
	 * Blast radius around the point of impact, in world units.
	 *
	 * Above zero, everything hostile inside takes the full damage once - the
	 * same rule a guard's melee arc already uses, rather than a falloff curve
	 * that would make the number on screen disagree with the number in design.
	 *
	 * EXACTLY ZERO means strictly single target: only the body the projectile
	 * physically struck is damaged, and a second enemy standing against it is
	 * not. That is not the same as a very small radius - a sphere even a few
	 * units wide still reaches a neighbouring capsule - which is why zero is
	 * handled as its own case rather than as a small number.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile", meta = (ClampMin = "0.0"))
	float SplashRadius = 96.0f;

	/**
	 * How far up the SPRITE is drawn from the row the arrow actually flies on.
	 *
	 * Visual only - it must never move the actor. See the class comment: this
	 * is the difference between an arrow that looks like it leaves the bow and
	 * an arrow that cannot hit anything standing level with the archer.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile")
	float VisualHeightOffset = 0.0f;

	/**
	 * Backstop only. The range check ends the flight long before this; it
	 * exists so a projectile spawned without Launch cannot live forever.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Projectile", meta = (ClampMin = "0.1"))
	float MaxLifetime = 5.0f;

	/** Draws the flight sweep and the blast radius. Prototype aid only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Debug")
	bool bDrawFlight = false;

	// ------------------------------------------------------------------
	// Runtime
	// ------------------------------------------------------------------

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Projectile")
	FVector Direction = FVector::ZeroVector;

	/** Screen-up in world space, from the shooter. Only lifts the sprite. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Projectile")
	FVector UpVector = FVector(0.0f, 0.0f, 1.0f);

	/**
	 * The lift actually applied to the sprite: VisualHeightOffset along
	 * UpVector with any component ALONG the flight line removed.
	 *
	 * Screen-up is the direction an Up or Down shot travels. Lifting the sprite
	 * along it therefore slides the visible projectile ahead of - or behind -
	 * the collision it stands for, which is precisely "the arrow passes through
	 * an enemy and nothing happens". Keeping only the perpendicular part leaves
	 * a Left/Right shot riding at bow height, where the lift costs nothing, and
	 * draws an Up/Down shot exactly on the line it is swept along.
	 */
	FVector VisualOffset = FVector::ZeroVector;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Projectile")
	EPTKTeam OwningTeam = EPTKTeam::Guards;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Projectile")
	TObjectPtr<AActor> SourceActor;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Projectile")
	float DistanceTravelled = 0.0f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Projectile")
	float TimeAlive = 0.0f;

	/** True once it has hit or expired: it stops moving and stops testing. */
	bool bSpent = false;

	/** False until Launch runs, so a mis-spawned projectile never flies. */
	bool bLaunched = false;
};
